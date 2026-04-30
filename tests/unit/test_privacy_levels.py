"""Tests de DataLevel y registry de privacy (P2.1, ADR-036)."""

from __future__ import annotations

from guia.privacy import (
    DataLevel,
    SOURCE_REGISTRY,
    data_classification,
    level_for,
    max_level_for_sources,
)
from guia.privacy.levels import get_method_level


# ── DataLevel ordenamiento ────────────────────────────────────────────────


def test_data_level_ordering() -> None:
    """L0 < L1 < L2 < L3 — orden lexicográfico = severidad."""
    assert DataLevel.L0_PUBLIC < DataLevel.L1_INTERNAL
    assert DataLevel.L1_INTERNAL < DataLevel.L2_PERSONAL
    assert DataLevel.L2_PERSONAL < DataLevel.L3_RESTRICTED


def test_data_level_max_combines_correctly() -> None:
    """max() aplica regla MAX-LEVEL-WINS."""
    levels = [DataLevel.L0_PUBLIC, DataLevel.L2_PERSONAL, DataLevel.L1_INTERNAL]
    assert max(levels) == DataLevel.L2_PERSONAL


def test_data_level_int_values() -> None:
    """Los valores enteros permiten persistencia simple."""
    assert int(DataLevel.L0_PUBLIC) == 0
    assert int(DataLevel.L3_RESTRICTED) == 3


# ── @data_classification decorator ────────────────────────────────────────


def test_decorator_attaches_level() -> None:
    @data_classification(DataLevel.L2_PERSONAL)
    def get_loans(patron_id: int):
        return []

    assert get_method_level(get_loans) == DataLevel.L2_PERSONAL


def test_decorator_undecorated_method_has_no_level() -> None:
    def search_catalog(query: str):
        return []

    assert get_method_level(search_catalog) is None


def test_decorator_preserves_function_behavior() -> None:
    @data_classification(DataLevel.L0_PUBLIC)
    def double(x: int) -> int:
        return x * 2

    assert double(5) == 10
    assert get_method_level(double) == DataLevel.L0_PUBLIC


# ── Registry / level_for ──────────────────────────────────────────────────


def test_level_for_known_public_sources() -> None:
    assert level_for("dspace") == DataLevel.L0_PUBLIC
    assert level_for("ojs") == DataLevel.L0_PUBLIC
    assert level_for("alicia") == DataLevel.L0_PUBLIC
    assert level_for("openalex") == DataLevel.L0_PUBLIC


def test_level_for_koha_catalog_is_public() -> None:
    """El catálogo de Koha es público (libros disponibles)."""
    assert level_for("koha") == DataLevel.L0_PUBLIC


def test_level_for_koha_loans_is_personal() -> None:
    """Los préstamos del usuario son L2 — guardrail crítico."""
    assert level_for("koha-loans") == DataLevel.L2_PERSONAL


def test_level_for_sis_erp_is_personal() -> None:
    """Sistemas con notas y finanzas personales."""
    assert level_for("sis") == DataLevel.L2_PERSONAL
    assert level_for("erp") == DataLevel.L2_PERSONAL


def test_level_for_rrhh_is_restricted() -> None:
    assert level_for("rrhh") == DataLevel.L3_RESTRICTED
    assert level_for("salud") == DataLevel.L3_RESTRICTED
    assert level_for("embargoed-thesis") == DataLevel.L3_RESTRICTED


def test_level_for_unknown_defaults_internal() -> None:
    """Default conservador: fuente desconocida → L1_INTERNAL (no L0)."""
    assert level_for("alguna_fuente_desconocida") == DataLevel.L1_INTERNAL


# ── max_level_for_sources ─────────────────────────────────────────────────


def test_max_level_empty_returns_l0() -> None:
    assert max_level_for_sources([]) == DataLevel.L0_PUBLIC


def test_max_level_single_source() -> None:
    assert max_level_for_sources(["dspace"]) == DataLevel.L0_PUBLIC
    assert max_level_for_sources(["sis"]) == DataLevel.L2_PERSONAL


def test_max_level_combines_to_strictest() -> None:
    """DSpace (L0) + Koha-loans (L2) → L2 wins."""
    sources = ["dspace", "ojs", "koha-loans"]
    assert max_level_for_sources(sources) == DataLevel.L2_PERSONAL


def test_max_level_l3_dominates() -> None:
    """L3 gana sobre cualquier combinación."""
    sources = ["dspace", "ojs", "rrhh", "sis"]
    assert max_level_for_sources(sources) == DataLevel.L3_RESTRICTED


# ── Cobertura del registry ────────────────────────────────────────────────


def test_registry_covers_all_known_audit_sources() -> None:
    """Las fuentes que aparecen en sources_used del audit deben estar registradas.

    Lista derivada de chat.py: 'pgvector', 'opensearch', 'koha'.
    Si se agrega una nueva, este test la fuerza al registry.
    """
    expected_sources = {"pgvector", "opensearch", "koha"}
    for source in expected_sources:
        assert source in SOURCE_REGISTRY, f"Fuente '{source}' falta en SOURCE_REGISTRY"
