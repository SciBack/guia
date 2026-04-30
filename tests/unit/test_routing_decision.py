"""Tests del modelo RouteDecision y enums asociados (P1.2 — paso 1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from guia.routing import Gate, IntentCategory, PrivacyLevel, RouteDecision, Tier


def test_route_decision_minimal() -> None:
    """RouteDecision se construye con campos requeridos."""
    d = RouteDecision(
        intent=IntentCategory.GREETING,
        tier=Tier.T0_FAST,
        privacy=PrivacyLevel.CLOUD_OK,
        gate_used=Gate.RULES,
    )

    assert d.intent == IntentCategory.GREETING
    assert d.tier == Tier.T0_FAST
    assert d.privacy == PrivacyLevel.CLOUD_OK
    assert d.gate_used == Gate.RULES
    assert d.confidence == 1.0
    assert d.latency_ms == 0.0
    assert d.reason == ""


def test_route_decision_with_optional_fields() -> None:
    """RouteDecision acepta confidence, latency_ms y reason."""
    d = RouteDecision(
        intent=IntentCategory.RESEARCH_DEEP,
        tier=Tier.T2_DEEP,
        privacy=PrivacyLevel.CLOUD_OK,
        gate_used=Gate.EMBEDDING,
        confidence=0.78,
        latency_ms=1.5,
        reason="centroid:research_deep margin=0.12",
    )

    assert d.confidence == pytest.approx(0.78)
    assert d.latency_ms == pytest.approx(1.5)
    assert "research_deep" in d.reason


def test_route_decision_is_frozen() -> None:
    """RouteDecision es inmutable (frozen=True)."""
    d = RouteDecision(
        intent=IntentCategory.CAMPUS_PERSONAL,
        tier=Tier.T1_STD,
        privacy=PrivacyLevel.ALWAYS_LOCAL,
        gate_used=Gate.RULES,
    )
    with pytest.raises(ValidationError):
        d.tier = Tier.T2_DEEP  # type: ignore[misc]


def test_confidence_bounds() -> None:
    """confidence rechaza valores fuera de [0, 1]."""
    with pytest.raises(ValidationError):
        RouteDecision(
            intent=IntentCategory.UNKNOWN,
            tier=Tier.T1_STD,
            privacy=PrivacyLevel.CLOUD_OK,
            gate_used=Gate.FALLBACK,
            confidence=1.5,
        )

    with pytest.raises(ValidationError):
        RouteDecision(
            intent=IntentCategory.UNKNOWN,
            tier=Tier.T1_STD,
            privacy=PrivacyLevel.CLOUD_OK,
            gate_used=Gate.FALLBACK,
            confidence=-0.1,
        )


def test_latency_ms_non_negative() -> None:
    """latency_ms rechaza valores negativos."""
    with pytest.raises(ValidationError):
        RouteDecision(
            intent=IntentCategory.GREETING,
            tier=Tier.T0_FAST,
            privacy=PrivacyLevel.CLOUD_OK,
            gate_used=Gate.RULES,
            latency_ms=-1.0,
        )


def test_intent_category_covers_all_buckets() -> None:
    """Las 8 categorías esperadas están definidas."""
    expected = {
        "greeting",
        "command",
        "campus_personal",
        "campus_generico",
        "research_simple",
        "research_deep",
        "out_of_scope",
        "unknown",
    }
    actual = {c.value for c in IntentCategory}
    assert actual == expected


def test_tier_has_four_levels() -> None:
    """Cuatro tiers T0–T3 según ADR-028 revisado."""
    assert {t.value for t in Tier} == {"t0_fast", "t1_std", "t2_deep", "t3_reasoning"}


def test_privacy_level_binary() -> None:
    """PrivacyLevel es binario: ALWAYS_LOCAL o CLOUD_OK."""
    assert {p.value for p in PrivacyLevel} == {"always_local", "cloud_ok"}


def test_gate_includes_cache_and_fallback() -> None:
    """Gate cubre los 3 gates + cache + fallback."""
    assert {g.value for g in Gate} == {
        "rules",
        "embedding",
        "llm",
        "cache",
        "fallback",
    }
