"""Tests del CascadeRouter (orquestador, P1.2 paso 4)."""

from __future__ import annotations

import asyncio

import pytest

from guia.routing import (
    CascadeRouter,
    EmbeddingRouter,
    Gate,
    IntentCategory,
    PrivacyLevel,
    RuleBasedRouter,
    Tier,
)
from tests.unit.test_routing_embedding import FakeEmbedder


# ── Fake LLM classifier (Gate 3) ──────────────────────────────────────────


class FakeLLMClassifier:
    """Clasifica devolviendo siempre la misma categoría (configurable)."""

    def __init__(self, category: IntentCategory) -> None:
        self.category = category
        self.calls = 0

    def classify_category(self, query: str) -> IntentCategory:
        self.calls += 1
        return self.category


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def warm_embedding_router() -> EmbeddingRouter:
    r = EmbeddingRouter(FakeEmbedder())
    asyncio.run(r.warm_up())
    return r


@pytest.fixture
def cascade(warm_embedding_router: EmbeddingRouter) -> CascadeRouter:
    return CascadeRouter(
        rules=RuleBasedRouter(),
        embedding=warm_embedding_router,
    )


@pytest.fixture
def cascade_with_llm(warm_embedding_router: EmbeddingRouter) -> tuple[CascadeRouter, FakeLLMClassifier]:
    llm = FakeLLMClassifier(IntentCategory.RESEARCH_DEEP)
    cascade = CascadeRouter(
        rules=RuleBasedRouter(),
        embedding=warm_embedding_router,
        llm_classifier=llm,
    )
    return cascade, llm


# ── Gate 1 short-circuita ─────────────────────────────────────────────────


def test_greeting_resolved_in_gate1(cascade: CascadeRouter) -> None:
    qv = FakeEmbedder().embed_query("hola")
    d = cascade.decide("hola", qv)

    assert d.gate_used == Gate.RULES
    assert d.intent == IntentCategory.GREETING


def test_campus_personal_resolved_in_gate1_forces_local(cascade: CascadeRouter) -> None:
    qv = FakeEmbedder().embed_query("¿cuáles son mis notas?")
    d = cascade.decide("¿cuáles son mis notas?", qv)

    assert d.gate_used == Gate.RULES
    assert d.privacy == PrivacyLevel.ALWAYS_LOCAL


def test_command_resolved_in_gate1(cascade: CascadeRouter) -> None:
    qv = FakeEmbedder().embed_query("/help")
    d = cascade.decide("/help", qv)

    assert d.gate_used == Gate.RULES
    assert d.intent == IntentCategory.COMMAND


# ── Gate 2 cuando Gate 1 no matchea ───────────────────────────────────────


def test_research_falls_to_gate2(cascade: CascadeRouter) -> None:
    """Query de research que no es saludo ni patrón inequívoco va a Gate 2."""
    qv = FakeEmbedder().embed_query("busca tesis sobre machine learning")
    d = cascade.decide("busca tesis sobre machine learning", qv)

    assert d.gate_used == Gate.EMBEDDING
    assert d.intent in {IntentCategory.RESEARCH_SIMPLE, IntentCategory.RESEARCH_DEEP}


def test_research_deep_falls_to_gate2(cascade: CascadeRouter) -> None:
    qv = FakeEmbedder().embed_query("compara metodologías y haz síntesis bibliométrico")
    d = cascade.decide("compara metodologías y haz síntesis bibliométrico", qv)

    assert d.gate_used == Gate.EMBEDDING
    assert d.intent == IntentCategory.RESEARCH_DEEP
    assert d.tier == Tier.T2_DEEP


# ── Gate 3 (LLM opt-in) ───────────────────────────────────────────────────


def test_gate3_invoked_when_gate2_low_confidence(
    cascade_with_llm: tuple[CascadeRouter, FakeLLMClassifier],
) -> None:
    """Si Gate 2 devuelve baja confianza, se invoca el LLM (Gate 3)."""
    cascade, llm = cascade_with_llm
    # Query sin keywords → vector uniforme → todos los centroides equidistantes
    # → confidence ~0 → Gate 3 se activa
    qv = FakeEmbedder().embed_query("xyzzy nonsense")
    d = cascade.decide("xyzzy nonsense", qv)

    assert d.gate_used == Gate.LLM
    assert d.intent == IntentCategory.RESEARCH_DEEP  # lo que el FakeLLM devolvió
    assert llm.calls == 1


def test_gate3_not_invoked_when_gate2_high_confidence(
    cascade_with_llm: tuple[CascadeRouter, FakeLLMClassifier],
) -> None:
    """Si Gate 2 está seguro, Gate 3 no se invoca aunque esté disponible."""
    cascade, llm = cascade_with_llm
    qv = FakeEmbedder().embed_query("compara metodologías síntesis bibliométrico tendencias")
    d = cascade.decide("compara metodologías síntesis", qv)

    assert d.gate_used == Gate.EMBEDDING
    assert llm.calls == 0


def test_gate3_skipped_when_no_llm_available(cascade: CascadeRouter) -> None:
    """Sin LLM clasificador, Gate 2 se respeta aunque tenga baja confianza."""
    qv = FakeEmbedder().embed_query("xyzzy nonsense")
    d = cascade.decide("xyzzy nonsense", qv)

    # Gate 2 decidió aunque sea con baja confianza
    assert d.gate_used == Gate.EMBEDDING


# ── Fallback cuando embedding no está warm ────────────────────────────────


def test_fallback_when_embedding_not_warm() -> None:
    """Si el EmbeddingRouter no está warm, se devuelve fallback."""
    cascade = CascadeRouter(
        rules=RuleBasedRouter(),
        embedding=EmbeddingRouter(FakeEmbedder()),  # SIN warm_up
    )
    qv = [0.0, 0.0, 0.0, 0.0]
    d = cascade.decide("query desconocida sin keywords", qv)

    assert d.gate_used == Gate.FALLBACK
    assert d.intent == IntentCategory.UNKNOWN
    assert d.tier == Tier.T1_STD
    assert d.privacy == PrivacyLevel.CLOUD_OK


# ── Latencia acumulada ────────────────────────────────────────────────────


def test_latency_is_recorded(cascade: CascadeRouter) -> None:
    qv = FakeEmbedder().embed_query("hola")
    d = cascade.decide("hola", qv)
    assert d.latency_ms >= 0.0
