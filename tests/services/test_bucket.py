"""Tests del bucket A/B determinístico para AgentOrchestrator (ADR-050, Día 3)."""

from __future__ import annotations

from guia.services._bucket import assign_bucket


# ── Anónimos siempre van a legacy ─────────────────────────────────────────────

def test_none_user_id_is_legacy() -> None:
    """user_id=None → legacy sin importar rollout."""
    assert assign_bucket(None, rollout_pct=100) == "legacy"


def test_empty_string_user_id_is_legacy() -> None:
    """user_id='' → legacy sin importar rollout."""
    assert assign_bucket("", rollout_pct=100) == "legacy"


def test_anon_prefix_lowercase_is_legacy() -> None:
    """'anon-xyz' empieza con 'anon' → legacy."""
    assert assign_bucket("anon-xyz", rollout_pct=100) == "legacy"


def test_anon_prefix_uppercase_is_legacy() -> None:
    """'ANON-123' (mayúsculas) → legacy (comparación case-insensitive)."""
    assert assign_bucket("ANON-123", rollout_pct=100) == "legacy"


def test_anonymous_literal_is_legacy() -> None:
    """'anonymous' empieza con 'anon' → legacy."""
    assert assign_bucket("anonymous", rollout_pct=100) == "legacy"


# ── Rollout extremos ──────────────────────────────────────────────────────────

def test_rollout_zero_all_legacy() -> None:
    """rollout_pct=0 → todos los usuarios van a legacy."""
    for uid in ["user-001", "student-42", "prof-99", "keycloak-uuid-abc"]:
        assert assign_bucket(uid, rollout_pct=0) == "legacy", f"Failed for {uid!r}"


def test_rollout_100_all_agent_except_anon() -> None:
    """rollout_pct=100 → todos los usuarios no-anónimos van a agent."""
    for uid in ["user-001", "student-42", "prof-99", "keycloak-uuid-abc"]:
        assert assign_bucket(uid, rollout_pct=100) == "agent", f"Failed for {uid!r}"
    # Anónimos siguen en legacy aunque rollout=100
    assert assign_bucket("anon-session", rollout_pct=100) == "legacy"
    assert assign_bucket(None, rollout_pct=100) == "legacy"


# ── Determinismo ──────────────────────────────────────────────────────────────

def test_determinism_same_user_same_bucket() -> None:
    """El mismo user_id siempre cae al mismo bucket en 1000 llamadas."""
    uid = "upeu-student-70123456"
    first_result = assign_bucket(uid, rollout_pct=50)
    for _ in range(999):
        assert assign_bucket(uid, rollout_pct=50) == first_result


# ── Distribución aproximada ───────────────────────────────────────────────────

def test_distribution_rollout_50_approximately_half() -> None:
    """Con rollout=50 y 1000 user_ids sintéticos, entre 45-55% caen en 'agent'."""
    user_ids = [f"user-{i:04d}" for i in range(1000)]
    agent_count = sum(1 for uid in user_ids if assign_bucket(uid, rollout_pct=50) == "agent")
    assert 450 <= agent_count <= 550, (
        f"Distribución fuera del margen: {agent_count}/1000 en 'agent' "
        f"(esperado 450-550 para rollout=50)"
    )
