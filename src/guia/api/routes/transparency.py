"""Endpoint de transparencia algorítmica (ADR-047, DS 115-2025-PCM)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from guia.config import GUIASettings
from guia.services.acceso_iga import LIMITE_INFRANQUEABLE, QUE_ABRE_CADA_NIVEL

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
        # Qué se le enseña a quién, según el IGA (MidPoint). Se publica
        # porque un nivel de acceso que solo existe dentro del código no es
        # gobernanza: nadie de fuera puede comprobarlo.
        "access_levels": {
            "governed_by": "MidPoint (IGA institucional), vía la sesión de Keycloak",
            "levels": {
                nivel.value: descripcion
                for nivel, descripcion in QUE_ABRE_CADA_NIVEL.items()
            },
            "invariant": LIMITE_INFRANQUEABLE,
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


@router.post("/recalcular")
async def recalcular(request: Request) -> dict:
    """Recuenta el índice. Lo llama la cosecha nocturna cuando termina.

    Sin esto, el inventario sería el del último arranque: la cosecha diaria
    añadiría documentos y la cifra publicada seguiría siendo la de ayer — el
    mismo defecto que tenía la lista escrita a mano, solo que más lento.

    Cerrado a la red local. Es un endpoint de escritura —dispara una
    agregación sobre toda la tabla de vectores— y no hay ninguna razón para
    que se pueda invocar desde fuera del servidor.
    """
    cliente = request.client.host if request.client else ""
    if cliente not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=404)

    import asyncio

    from guia.services.analitica_del_indice import CalculadoraDeAnalitica

    settings: GUIASettings = request.app.state.settings
    calculadora = CalculadoraDeAnalitica(settings.pgvector_database_url)
    analitica = await asyncio.to_thread(calculadora.calcular)
    request.app.state.analitica_del_indice = analitica

    chat = getattr(request.app.state.container, "chat_service", None)
    if chat is not None and hasattr(chat, "refrescar_inventario"):
        chat.refrescar_inventario(analitica)

    return {
        "recalculado": True,
        "fuentes": len(analitica.fuentes),
        "documentos": analitica.total,
    }
