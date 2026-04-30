"""Tests del PrivacyRouter (P2.2, ADR-036)."""

from __future__ import annotations

import pytest

from guia.privacy import DataLevel, PrivacyRouter


@pytest.fixture
def router() -> PrivacyRouter:
    return PrivacyRouter()


# ── Sources puros (sin PII) ───────────────────────────────────────────────


def test_only_public_sources_returns_l0(router: PrivacyRouter) -> None:
    v = router.evaluate("busca tesis sobre IA", ["dspace", "ojs"])
    assert v.final_level == DataLevel.L0_PUBLIC
    assert v.force_local is False
    assert v.pii_in_query is False


def test_personal_source_forces_local(router: PrivacyRouter) -> None:
    """Tocar koha-loans → L2 → force_local=True."""
    v = router.evaluate("alguna query genérica", ["koha-loans"])
    assert v.final_level == DataLevel.L2_PERSONAL
    assert v.force_local is True


def test_restricted_source_forces_local(router: PrivacyRouter) -> None:
    v = router.evaluate("query", ["rrhh"])
    assert v.final_level == DataLevel.L3_RESTRICTED
    assert v.force_local is True


def test_unknown_source_defaults_to_internal_no_force(router: PrivacyRouter) -> None:
    """Fuente desconocida → L1_INTERNAL → cloud_ok (no force_local)."""
    v = router.evaluate("query", ["fuente_marciana"])
    assert v.final_level == DataLevel.L1_INTERNAL
    assert v.force_local is False


# ── PII en query ──────────────────────────────────────────────────────────


def test_dni_in_query_forces_local(router: PrivacyRouter) -> None:
    """8 dígitos en la query → DNI peruano → L2 → force_local."""
    v = router.evaluate("mi DNI es 70123456 y necesito ayuda", ["dspace"])
    assert v.pii_in_query is True
    assert v.final_level >= DataLevel.L2_PERSONAL
    assert v.force_local is True


def test_email_institucional_in_query_forces_local(router: PrivacyRouter) -> None:
    v = router.evaluate("mi correo es alumno@upeu.edu.pe", ["dspace"])
    assert v.pii_in_query is True
    assert v.force_local is True


def test_personal_possessive_in_query_forces_local(router: PrivacyRouter) -> None:
    """'mis notas', 'mi deuda' marcan PII personal aunque no haya DNI."""
    v = router.evaluate("¿cuáles son mis notas?", ["dspace"])
    assert v.pii_in_query is True
    assert v.force_local is True


def test_no_pii_no_pp_does_not_force_local(router: PrivacyRouter) -> None:
    """Query sin PII y solo sources públicos → cloud_ok."""
    v = router.evaluate("¿qué tesis hay sobre teología sistemática?", ["dspace"])
    assert v.pii_in_query is False
    assert v.force_local is False


def test_short_numbers_are_not_dni(router: PrivacyRouter) -> None:
    """Números cortos (4-7 dígitos) no son DNI."""
    v = router.evaluate("la tesis del 2024 con código 1234567", ["dspace"])
    # 7 dígitos no son DNI (8). 1234567 NO matchea.
    assert v.pii_in_query is False


def test_dni_with_surrounding_digits_is_not_dni(router: PrivacyRouter) -> None:
    """123456789 (9 dígitos) NO es DNI peruano (son 8)."""
    v = router.evaluate("código 123456789", ["dspace"])
    # _DNI_RE usa lookbehind/lookahead anti-dígitos, no matchea.
    assert v.pii_in_query is False


# ── PII en docs ───────────────────────────────────────────────────────────


def test_pii_in_docs_forces_local(router: PrivacyRouter) -> None:
    docs = "Contexto: el estudiante con DNI 70123456 ..."
    v = router.evaluate("query inocua", ["dspace"], retrieved_docs_text=docs)
    assert v.pii_in_docs is True
    assert v.force_local is True


def test_pii_in_docs_email(router: PrivacyRouter) -> None:
    docs = "Documento: Pérez García (ja.perez@upeu.edu.pe)..."
    v = router.evaluate("query", ["dspace"], retrieved_docs_text=docs)
    assert v.pii_in_docs is True


# ── MAX-LEVEL-WINS ────────────────────────────────────────────────────────


def test_max_level_wins_query_over_sources(router: PrivacyRouter) -> None:
    """Sources L0 + query L2 → final L2."""
    v = router.evaluate("¿cuál es mi promedio?", ["dspace"])
    assert v.level_sources == DataLevel.L0_PUBLIC
    assert v.level_query == DataLevel.L2_PERSONAL
    assert v.final_level == DataLevel.L2_PERSONAL


def test_max_level_wins_l3_dominates(router: PrivacyRouter) -> None:
    """Sources L3 + query L0 → final L3."""
    v = router.evaluate("query inocua", ["rrhh"])
    assert v.final_level == DataLevel.L3_RESTRICTED


# ── Reason para audit ─────────────────────────────────────────────────────


def test_reason_documents_decision(router: PrivacyRouter) -> None:
    v = router.evaluate("¿cuáles son mis notas? DNI 70123456", ["dspace"])
    assert "pii_query" in v.reason
    assert "L2_PERSONAL" in v.reason or "L3_RESTRICTED" in v.reason
