"""Routing layer — cascada de gates para selección de modelo y privacidad.

Diseñado en ADR-028 revisado y formalizado en roadmap-v1 P1.2.

Tres gates ordenados por costo creciente:
- Gate 1: RuleBasedRouter (~0ms) — saludos, patrones inequívocos, comandos
- Gate 2: EmbeddingRouter (~1ms) — cosine similarity contra 4 centroides
- Gate 3: IntentClassifier (~150-300ms, opt-in) — solo si Gate 2 ambiguo

Cada gate retorna RouteDecision o None (no decidió). El CascadeRouter
orquesta la cascada y agrega métricas de latencia por gate.
"""

from guia.routing.cascade import CascadeRouter
from guia.routing.decision import (
    Gate,
    IntentCategory,
    PrivacyLevel,
    RouteDecision,
    Tier,
)
from guia.routing.embedding import EmbeddingRouter
from guia.routing.rules import RuleBasedRouter

__all__ = [
    "CascadeRouter",
    "EmbeddingRouter",
    "Gate",
    "IntentCategory",
    "PrivacyLevel",
    "RouteDecision",
    "RuleBasedRouter",
    "Tier",
]
