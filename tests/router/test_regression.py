"""Suite gold-standard de regresión P1.2 (50 queries representativas).

Métricas que valida:
1. Precisión de clasificación: cada query produce el (intent, privacy, tier) esperado
2. Eficiencia: ≥70% de queries se resuelven en Gate 1 o Gate 2 (sin LLM)
3. Distribución de gates registrada para detectar drift en el futuro

La suite vive bajo tests/router/ porque el FakeEmbedder de routing/embedding
es determinístico — no necesita pgvector ni red.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml

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

QUERIES_PATH = Path(__file__).parent / "regression_queries.yaml"


def _load_queries() -> list[dict]:
    with QUERIES_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def cascade() -> CascadeRouter:
    embedding = EmbeddingRouter(FakeEmbedder())
    asyncio.run(embedding.warm_up())
    return CascadeRouter(rules=RuleBasedRouter(), embedding=embedding)


@pytest.fixture(scope="module")
def queries() -> list[dict]:
    qs = _load_queries()
    assert len(qs) == 50, f"esperaba 50 queries, hay {len(qs)}"
    return qs


# ── Test parametrizado por query ──────────────────────────────────────────


def _ids(qs: list[dict]) -> list[str]:
    return [f"{q['intent']}: {q['query'][:40]}" for q in qs]


@pytest.mark.parametrize("q", _load_queries(), ids=_ids(_load_queries()))
def test_each_query_produces_expected_decision(
    cascade: CascadeRouter, q: dict
) -> None:
    """Cada query produce intent + privacy + tier + gate correctos."""
    embedder = FakeEmbedder()
    qv = embedder.embed_query(q["query"])
    d = cascade.decide(q["query"], qv)

    expected_intent = IntentCategory(q["intent"])
    expected_privacy = PrivacyLevel(q["privacy"])
    expected_tier = Tier(q["tier"])
    expected_gate = Gate(q["expected_gate"])

    assert d.intent == expected_intent, (
        f"query={q['query']!r} → intent={d.intent.value} (esperaba {expected_intent.value})"
    )
    assert d.privacy == expected_privacy, (
        f"query={q['query']!r} → privacy={d.privacy.value} (esperaba {expected_privacy.value})"
    )
    assert d.tier == expected_tier, (
        f"query={q['query']!r} → tier={d.tier.value} (esperaba {expected_tier.value})"
    )
    assert d.gate_used == expected_gate, (
        f"query={q['query']!r} → gate={d.gate_used.value} (esperaba {expected_gate.value})"
    )


# ── Métricas agregadas ────────────────────────────────────────────────────


def test_at_least_70_percent_resolved_in_gate1_or_gate2(
    cascade: CascadeRouter, queries: list[dict]
) -> None:
    """Métrica clave del roadmap-v1 P1.2: ≥70% sin invocar LLM (Gate 3)."""
    embedder = FakeEmbedder()
    cheap_gates = {Gate.RULES, Gate.EMBEDDING}
    cheap_count = 0

    for q in queries:
        qv = embedder.embed_query(q["query"])
        d = cascade.decide(q["query"], qv)
        if d.gate_used in cheap_gates:
            cheap_count += 1

    pct = cheap_count / len(queries)
    assert pct >= 0.70, f"solo {pct:.1%} resueltas en Gate 1+2 (umbral 70%)"


def test_no_query_falls_to_fallback(
    cascade: CascadeRouter, queries: list[dict]
) -> None:
    """Ninguna query del gold-standard debería caer al fallback."""
    embedder = FakeEmbedder()
    fallbacks: list[str] = []

    for q in queries:
        qv = embedder.embed_query(q["query"])
        d = cascade.decide(q["query"], qv)
        if d.gate_used == Gate.FALLBACK:
            fallbacks.append(q["query"])

    assert not fallbacks, f"queries cayeron al fallback: {fallbacks}"


def test_all_campus_personal_forces_local(
    cascade: CascadeRouter, queries: list[dict]
) -> None:
    """Guardrail de privacidad: TODA query etiquetada campus_personal → ALWAYS_LOCAL."""
    embedder = FakeEmbedder()
    for q in queries:
        if q["intent"] != "campus_personal":
            continue
        qv = embedder.embed_query(q["query"])
        d = cascade.decide(q["query"], qv)
        assert d.privacy == PrivacyLevel.ALWAYS_LOCAL, (
            f"FUGA DE PRIVACIDAD: {q['query']!r} debería ser ALWAYS_LOCAL"
        )
