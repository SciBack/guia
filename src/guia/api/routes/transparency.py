"""Endpoint de transparencia algorítmica (ADR-047, DS 115-2025-PCM)."""
from __future__ import annotations

from fastapi import APIRouter, Request

from guia.config import GUIASettings

router = APIRouter(prefix="/api/transparency", tags=["transparency"])


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
        "data_sources": [
            {"name": "Koha UPeU", "type": "biblioteca", "records_approx": 35000},
            {"name": "OJS revistas.upeu.edu.pe", "type": "revistas_academicas", "records_approx": 744},
        ],
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
