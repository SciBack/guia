"""Tipos compartidos del routing layer (ADR-028 revisado, P1.2)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class IntentCategory(StrEnum):
    """Categorías que distinguen privacidad y profundidad de la query.

    Más granular que el Intent del dominio (RESEARCH/CAMPUS/GENERAL/OUT_OF_SCOPE).
    Una query CAMPUS puede ser PERSONAL (ALWAYS_LOCAL, fuerza Ollama) o GENERICO
    (CLOUD_OK, puede ir a Claude). RESEARCH se subdivide por profundidad para
    elegir entre Haiku y Sonnet.
    """

    GREETING = "greeting"  # saludos, cortesía, meta-preguntas sobre GUIA
    COMMAND = "command"  # comandos directos (/help, /reset, /lang)
    CAMPUS_PERSONAL = "campus_personal"  # mis notas, mi deuda, mi perfil
    CAMPUS_GENERICO = "campus_generico"  # horarios, calendario, eventos públicos
    RESEARCH_SIMPLE = "research_simple"  # catálogo, "¿hay X?", lookup directo
    RESEARCH_DEEP = "research_deep"  # síntesis multi-doc, comparativas, marcos
    OUT_OF_SCOPE = "out_of_scope"  # fuera del alcance institucional
    UNKNOWN = "unknown"  # ningún gate pudo decidir


class Tier(StrEnum):
    """Tier de modelo LLM según complejidad (ADR-028 revisado, tabla T0–T3)."""

    T0_FAST = "t0_fast"  # Qwen 2.5 3B (idem cloud) — saludos, lookup, <1s
    T1_STD = "t1_std"  # Qwen 2.5 7B / Claude Haiku — RAG estándar, 3–5s
    T2_DEEP = "t2_deep"  # DeepSeek R1 / Claude Sonnet — síntesis 10+ docs, 8–15s
    T3_REASONING = "t3_reasoning"  # Claude Sonnet thinking — multi-step, 15–30s


class PrivacyLevel(StrEnum):
    """Política de privacidad para la ejecución del LLM (ADR-036).

    El nivel se determina por la INTERSECCIÓN de:
    1. PII en la query
    2. DataLevel L0–L3 de los adapters que se van a tocar
    3. PII en docs recuperados

    Aquí solo modelamos el resultado: ¿la query puede ir a cloud o no?
    """

    ALWAYS_LOCAL = "always_local"  # L2/L3 — nunca sale del nodo
    CLOUD_OK = "cloud_ok"  # L0/L1 — cloud permitido (ZDR si aplica)


class Gate(StrEnum):
    """Gate de la cascada que tomó la decisión (para audit y métricas)."""

    RULES = "rules"  # Gate 1 — RuleBasedRouter
    EMBEDDING = "embedding"  # Gate 2 — EmbeddingRouter
    LLM = "llm"  # Gate 3 — IntentClassifier (opt-in)
    CACHE = "cache"  # caché semántico (Redis hit antes de gates)
    FALLBACK = "fallback"  # decisión por defecto cuando ningún gate decidió


class RouteDecision(BaseModel):
    """Decisión combinada de la cascada de routers.

    Producida por CascadeRouter.decide() y consumida por ChatService.answer()
    para inyectar el LLM correcto en el flujo de síntesis.
    """

    model_config = ConfigDict(frozen=True)

    intent: IntentCategory
    tier: Tier
    privacy: PrivacyLevel
    gate_used: Gate
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    """Confianza de la decisión [0, 1]. Útil para Gate 3 opt-in cuando margin < 0.05."""

    latency_ms: float = Field(default=0.0, ge=0.0)
    """Latencia total acumulada de los gates atravesados (para métricas)."""

    reason: str = ""
    """Texto breve para audit log y debug ('greeting matched', 'centroid:research_deep')."""
