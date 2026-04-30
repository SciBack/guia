"""CascadeRouter — orquesta los 3 gates en orden de costo creciente.

Flujo:
    Gate 1 (rules, ~0ms)   → si match, retorna
    Gate 2 (embedding, ~1ms) → si confidence ≥ umbral, retorna
    Gate 3 (LLM, opt-in)    → solo si Gate 2 ambiguo
    Fallback                 → RouteDecision(UNKNOWN, T1_STD, CLOUD_OK)

Cada gate suma su latencia a la decisión final para métricas/observabilidad.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Protocol

from guia.routing.decision import (
    Gate,
    IntentCategory,
    PrivacyLevel,
    RouteDecision,
    Tier,
)

if TYPE_CHECKING:
    from guia.routing.embedding import EmbeddingRouter
    from guia.routing.rules import RuleBasedRouter


class IntentLLMClassifier(Protocol):
    """Contrato del Gate 3 (LLM classifier opt-in).

    Mantiene el método existente IntentClassifier.classify_sync() pero
    devuelve IntentCategory en vez de Intent legacy. Implementación
    pendiente; por ahora opcional (CascadeRouter funciona sin Gate 3).
    """

    def classify_category(self, query: str) -> IntentCategory: ...


# Threshold de confianza por debajo del cual se activa Gate 3 (si está disponible).
# Mapeo del roadmap "margin entre top-1 y top-2 < 0.05": como confidence se calcula
# como min(1, margin/0.10), un margin de 0.05 equivale a confidence 0.5.
_CONFIDENCE_THRESHOLD_FOR_GATE3 = 0.50


class CascadeRouter:
    """Orquesta la cascada de 3 gates.

    Args:
        rules: Gate 1 — RuleBasedRouter.
        embedding: Gate 2 — EmbeddingRouter (debe llamarse warm_up antes).
        llm_classifier: Gate 3 opcional. Si es None, no se invoca y se acepta
            la decisión de Gate 2 aunque tenga baja confianza.
        gate3_threshold: confidence < este valor activa Gate 3 (default 0.30).
    """

    def __init__(
        self,
        rules: RuleBasedRouter,
        embedding: EmbeddingRouter,
        llm_classifier: IntentLLMClassifier | None = None,
        gate3_threshold: float = _CONFIDENCE_THRESHOLD_FOR_GATE3,
    ) -> None:
        self._rules = rules
        self._embedding = embedding
        self._llm = llm_classifier
        self._gate3_threshold = gate3_threshold

    def decide(self, query: str, query_vector: list[float]) -> RouteDecision:
        """Resuelve la cascada y retorna una RouteDecision (nunca None)."""
        t_start = time.perf_counter()

        # ── Gate 1: reglas deterministas ──────────────────────────────────
        decision = self._rules.decide(query)
        if decision is not None:
            return decision

        # ── Gate 2: embedding similarity ──────────────────────────────────
        decision = self._embedding.decide(query_vector)

        if decision is None:
            # Embedding router no warm: fallback seguro
            return self._fallback(t_start, "embedding router not warm")

        # ── Gate 3: LLM classifier (opt-in) ───────────────────────────────
        if self._llm is not None and decision.confidence < self._gate3_threshold:
            return self._invoke_gate3(query, decision, t_start)

        return decision

    def _invoke_gate3(
        self,
        query: str,
        gate2_decision: RouteDecision,
        t_start: float,
    ) -> RouteDecision:
        """Activa el LLM classifier para resolver ambigüedad de Gate 2.

        Conserva el tier/privacy mapeados desde la categoría que el LLM
        elige (vía tabla _CATEGORY_TO_TIER_PRIVACY).
        """
        assert self._llm is not None
        category = self._llm.classify_category(query)
        tier, privacy = _category_to_tier_privacy(category)

        latency_ms = (time.perf_counter() - t_start) * 1000
        return RouteDecision(
            intent=category,
            tier=tier,
            privacy=privacy,
            gate_used=Gate.LLM,
            confidence=0.85,  # LLM clasificó explícitamente; alta confianza
            latency_ms=latency_ms,
            reason=f"llm_classifier (gate2_margin_low: {gate2_decision.confidence:.2f})",
        )

    def _fallback(self, t_start: float, reason: str) -> RouteDecision:
        """Decisión por defecto cuando ningún gate pudo decidir."""
        latency_ms = (time.perf_counter() - t_start) * 1000
        return RouteDecision(
            intent=IntentCategory.UNKNOWN,
            tier=Tier.T1_STD,  # default conservador
            privacy=PrivacyLevel.CLOUD_OK,  # default conservador
            gate_used=Gate.FALLBACK,
            confidence=0.0,
            latency_ms=latency_ms,
            reason=reason,
        )


# ── Mapeo IntentCategory → (Tier, PrivacyLevel) ──────────────────────────
# Replica la lógica del EmbeddingRouter para uso desde Gate 3.

_CATEGORY_TO_TIER_PRIVACY: dict[IntentCategory, tuple[Tier, PrivacyLevel]] = {
    IntentCategory.GREETING: (Tier.T0_FAST, PrivacyLevel.CLOUD_OK),
    IntentCategory.COMMAND: (Tier.T0_FAST, PrivacyLevel.CLOUD_OK),
    IntentCategory.CAMPUS_PERSONAL: (Tier.T1_STD, PrivacyLevel.ALWAYS_LOCAL),
    IntentCategory.CAMPUS_GENERICO: (Tier.T0_FAST, PrivacyLevel.CLOUD_OK),
    IntentCategory.RESEARCH_SIMPLE: (Tier.T1_STD, PrivacyLevel.CLOUD_OK),
    IntentCategory.RESEARCH_DEEP: (Tier.T2_DEEP, PrivacyLevel.CLOUD_OK),
    IntentCategory.OUT_OF_SCOPE: (Tier.T0_FAST, PrivacyLevel.CLOUD_OK),
    IntentCategory.UNKNOWN: (Tier.T1_STD, PrivacyLevel.CLOUD_OK),
}


def _category_to_tier_privacy(category: IntentCategory) -> tuple[Tier, PrivacyLevel]:
    return _CATEGORY_TO_TIER_PRIVACY[category]
