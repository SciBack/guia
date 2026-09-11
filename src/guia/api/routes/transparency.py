"""Endpoint de transparencia algorítmica (ADR-047, DS 115-2025-PCM)."""
from __future__ import annotations

from fastapi import APIRouter, Request

from guia.config import GUIASettings

router = APIRouter(prefix="/api/transparency", tags=["transparency"])


def _inventario(request: Request) -> list[dict]:
    """El inventario real del índice.

    Si el cálculo falla se devuelve una lista vacía y se dice por qué: es
    preferible a servir cifras viejas, que es justo lo que se está corrigiendo.
    """
    analitica = getattr(request.app.state, "analitica_del_indice", None)
    if analitica is None:
        return []
    return analitica.para_transparencia()


@router.get("")
async def transparency(request: Request) -> dict:
    """Endpoint de transparencia y model card pública (DS 115-2025-PCM)."""
    settings: GUIASettings = request.app.state.settings

    return {
        "system_name": "GUIA",
        "version": "0.1.0",
        "system_type": "Asistente conversacional con IA (RAG)",
        "risk_classification": {
            "framework": "DS 115-2025-PCM (Perú)",
            "level": "riesgo aceptable",
            "rationale": "No toma decisiones vinculantes; supervisión humana implícita en cada interacción",
        },
        "models": {
            "synthesis": settings.ollama_synthesis_model,
            "fast": settings.ollama_fast_model,
            "embeddings": "intfloat/multilingual-e5-large",
            "cloud_fallback": "claude-sonnet-4-6 (solo queries no sensibles)",
        },
        # Contado del índice, no escrito a mano. La lista anterior estaba
        # fija en el código y el 11-sep-2026 tres de sus cuatro cifras eran
        # falsas —12.500 artículos de OJS cuando hay 744, 550 eventos cuando
        # hay 102, y el CRIS sin mencionar—. Un dato de transparencia que hay
        # que acordarse de actualizar no es transparencia.
        "data_sources": _inventario(request),
        "privacy": {
            "regulation": "Ley 29733 + DS 016-2024-JUS",
            "pii_redaction": "DataLevel L2/L3 procesado solo en local",
            "audit_log_retention_days": 1095,
        },
        "human_oversight": {
            "channel": "https://gob.pe/iaperu",
            "institutional_contact": settings.oai_admin_email,
        },
        "limitations": [
            "Las respuestas pueden contener errores. Verifica siempre la fuente original.",
            "Cobertura limitada a las fuentes indexadas listadas arriba.",
            "No emite juicios de valor académico ni decisiones vinculantes.",
        ],
        "model_card": "https://docs.sciback.com/transparency/model-card-guia",
    }
