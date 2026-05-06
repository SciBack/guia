"""Modelos de chat_feedback — dataset de entrenamiento con consentimiento explícito.

A diferencia del audit_log (hash-only, compliance-first), aquí guardamos
query+respuesta+rating COMPLETOS, pero SOLO cuando el usuario hace clic
explícito en 👍/👎 (consentimiento Ley 29733 art. 5).

Cumple DS 115-2025-PCM art. 21.3 y la regla de minimización: nunca PII en
campos de texto libre — la PII se redacta antes de persistir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ChatFeedback:
    """Entrada del dataset de feedback (un par query→response calificado).

    Toda fila persistida implica consentimiento del usuario (clic en 👍/👎).
    """

    thread_id: str
    """ID del thread Chainlit donde ocurrió la conversación."""

    step_id: str
    """ID del step (mensaje) calificado."""

    user_id: str
    """ID del usuario en Keycloak (sub claim) o 'anonymous'."""

    query: str
    """Texto de la pregunta del usuario (PII redactada)."""

    response: str
    """Texto de la respuesta del asistente."""

    rating: int
    """+1 (👍) o -1 (👎). Valores fuera de {-1, +1} se rechazan."""

    sources: list[dict[str, Any]] = field(default_factory=list)
    """Fuentes recuperadas en el RAG: [{title, authors, year, url, score}, ...]"""

    intent: str | None = None
    """Intent clasificado para esta query (research_simple, campus_personal, ...)."""

    model_used: str | None = None
    """Modelo LLM que generó la respuesta (qwen3:8b, claude-sonnet-4-7, none)."""

    comment: str | None = None
    """Comentario opcional del usuario al rateá (Chainlit lo soporta nativo)."""

    pii_redacted: bool = False
    """True si se aplicó redacción de PII a query/response antes de persistir."""

    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
