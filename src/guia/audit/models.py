"""Modelos de audit log (ADR-036)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime


def hash_query(query: str) -> str:
    """Hash sha256 del texto de la query.

    REGLA NO-NEGOCIABLE: la query original NUNCA se persiste. Solo este hash.
    Permite detectar repetición de queries (caché) y debugging por hash sin
    exponer contenido sensible. Cumplimiento Ley 29733 art. 13.
    """
    return hashlib.sha256(query.strip().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditLogEntry:
    """Entrada del audit log para una sola query.

    NO contiene la query original — solo su hash. NO contiene la respuesta
    del LLM ni los documentos recuperados — solo IDs/nombres de fuentes.
    """

    user_id: str
    """ID del usuario en Keycloak (sub claim) o 'anonymous'."""

    query_hash: str
    """sha256 hex de la query original. Nunca la query misma."""

    intent: str
    """Intent legacy (research/campus/general/out_of_scope) — del Intent enum."""

    privacy_level: str
    """always_local | cloud_ok — del PrivacyLevel enum del routing."""

    sources_used: list[str]
    """Lista de fuentes consultadas: ['dspace', 'koha', 'ojs', ...]."""

    llm_model: str
    """Modelo LLM usado: 'qwen2.5:7b', 'claude-sonnet-4-7', 'none' (sin LLM)."""

    llm_provider: str
    """Proveedor: 'ollama-local' | 'anthropic-cloud' | 'cache' | 'none'."""

    gate_used: str = "unknown"
    """Gate de routing que decidió: rules/embedding/llm/cache/fallback."""

    session_id: str | None = None
    """ID de sesión Chainlit/Telegram (para correlacionar)."""

    pii_detected: bool = False
    """True si se detectó PII en query/contexto. P2.3 lo activará."""

    pii_redacted: bool = False
    """True si se redactó PII antes de cloud. P2.3 lo activará."""

    latency_ms: int = 0
    """Latencia total de la query en ms (clasificación + RAG + síntesis)."""

    cached: bool = False
    """True si la respuesta vino del caché semántico (sin invocar LLM)."""

    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
