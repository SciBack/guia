"""Routing layer — cascada de gates para selección de modelo y privacidad.

Diseñado en ADR-028 revisado y formalizado en roadmap-v1 P1.2.

Tres gates ordenados por costo creciente:
- Gate 1: RuleBasedRouter (~0ms) — saludos, patrones inequívocos, comandos
- Gate 2: EmbeddingRouter (~1ms) — cosine similarity contra 4 centroides
- Gate 3: IntentClassifier (~150-300ms, opt-in) — solo si Gate 2 ambiguo

Cada gate retorna RouteDecision o None (no decidió). El CascadeRouter
orquesta la cascada y agrega métricas de latencia por gate.
"""

from guia.domain.chat import Intent
from guia.routing.cascade import CascadeRouter
from guia.routing.decision import (
    Gate,
    IntentCategory,
    PrivacyLevel,
    RouteDecision,
    Tier,
)
from guia.routing.embedding import EmbeddingRouter
from guia.routing.intent import LLMIntentCategoryClassifier
from guia.routing.rules import RuleBasedRouter

# ── Mapeo IntentCategory (routing) → Intent legacy (domain) ──────────────
# El dominio trabaja con 4 intents (RESEARCH/CAMPUS/GENERAL/OUT_OF_SCOPE)
# que gobiernan el flujo de ChatService (RAG, Koha, mensajes especiales).
# Las 8 categorías de routing son más granulares — esta tabla las colapsa.

_CATEGORY_TO_INTENT: dict[IntentCategory, Intent] = {
    IntentCategory.GREETING: Intent.GENERAL,
    IntentCategory.COMMAND: Intent.GENERAL,
    IntentCategory.CAMPUS_PERSONAL: Intent.CAMPUS,
    IntentCategory.CAMPUS_GENERICO: Intent.CAMPUS,
    IntentCategory.RESEARCH_SIMPLE: Intent.RESEARCH,
    IntentCategory.RESEARCH_DEEP: Intent.RESEARCH,
    IntentCategory.OUT_OF_SCOPE: Intent.OUT_OF_SCOPE,
    IntentCategory.UNKNOWN: Intent.GENERAL,
}


def category_to_intent(category: IntentCategory) -> Intent:
    """Mapea IntentCategory (8 buckets) a Intent legacy (4 buckets)."""
    return _CATEGORY_TO_INTENT[category]


__all__ = [
    "CascadeRouter",
    "EmbeddingRouter",
    "Gate",
    "IntentCategory",
    "LLMIntentCategoryClassifier",
    "PrivacyLevel",
    "RouteDecision",
    "RuleBasedRouter",
    "Tier",
    "category_to_intent",
]
