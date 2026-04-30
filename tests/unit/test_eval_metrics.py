"""Tests del módulo eval/metrics — NDCG, recall, precision (P3.3)."""

from __future__ import annotations

import math

from guia.eval import ndcg_at_k, precision_at_k, recall_at_k
from guia.eval.metrics import dcg_at_k


# ── precision_at_k ───────────────────────────────────────────────────────


def test_precision_perfect_top_k() -> None:
    """Si los k primeros son todos relevantes → precision=1."""
    ranked = ["a", "b", "c", "d", "e"]
    expected = ["a", "b", "c"]
    assert precision_at_k(ranked, expected, 3) == 1.0


def test_precision_no_hits() -> None:
    ranked = ["x", "y", "z"]
    expected = ["a", "b"]
    assert precision_at_k(ranked, expected, 3) == 0.0


def test_precision_partial() -> None:
    ranked = ["a", "x", "b", "y"]
    expected = ["a", "b"]
    # 2 hits en top-4 → 0.5
    assert precision_at_k(ranked, expected, 4) == 0.5


def test_precision_k_zero() -> None:
    assert precision_at_k(["a"], ["a"], 0) == 0.0


# ── recall_at_k ──────────────────────────────────────────────────────────


def test_recall_all_relevant_in_top_k() -> None:
    ranked = ["a", "b", "x", "y"]
    expected = ["a", "b"]
    assert recall_at_k(ranked, expected, 4) == 1.0


def test_recall_partial() -> None:
    ranked = ["a", "x", "y", "z"]
    expected = ["a", "b"]
    # 1 de 2 relevantes encontrado en top-4 → 0.5
    assert recall_at_k(ranked, expected, 4) == 0.5


def test_recall_empty_expected_returns_zero() -> None:
    assert recall_at_k(["a"], [], 5) == 0.0


# ── dcg_at_k ─────────────────────────────────────────────────────────────


def test_dcg_perfect_ranking() -> None:
    """Todos relevantes en orden: DCG = 1/log2(2) + 1/log2(3) + ..."""
    rels = [1, 1, 1]
    expected = 1 / math.log2(2) + 1 / math.log2(3) + 1 / math.log2(4)
    assert math.isclose(dcg_at_k(rels, 3), expected)


def test_dcg_no_relevance() -> None:
    rels = [0, 0, 0]
    assert dcg_at_k(rels, 3) == 0.0


# ── ndcg_at_k ────────────────────────────────────────────────────────────


def test_ndcg_perfect_ranking_returns_one() -> None:
    """Si los k primeros son todos los relevantes en orden → NDCG=1."""
    ranked = ["a", "b", "c"]
    expected = ["a", "b", "c"]
    assert ndcg_at_k(ranked, expected, 3) == 1.0


def test_ndcg_partial_relevance() -> None:
    """Solo el primero es relevante → NDCG bajo pero > 0."""
    ranked = ["a", "x", "y"]
    expected = ["a"]
    # DCG = 1/log2(2) = 1
    # IDCG = 1/log2(2) = 1 (un solo relevante en top)
    # NDCG = 1.0
    assert ndcg_at_k(ranked, expected, 3) == 1.0


def test_ndcg_relevant_at_position_2_lower_than_position_1() -> None:
    """Relevant en pos 2 vs pos 1 → menor NDCG."""
    expected = ["a"]
    pos_1 = ndcg_at_k(["a", "x", "y"], expected, 3)
    pos_2 = ndcg_at_k(["x", "a", "y"], expected, 3)
    assert pos_1 > pos_2


def test_ndcg_no_relevant_returns_zero() -> None:
    assert ndcg_at_k(["a", "b"], [], 5) == 0.0
    assert ndcg_at_k(["a", "b"], ["x"], 5) == 0.0


def test_ndcg_in_unit_range() -> None:
    """NDCG siempre en [0, 1]."""
    expected = ["a", "b"]
    test_cases = [
        ["a", "b", "c"],   # perfecto
        ["c", "a", "b"],   # parcial
        ["x", "y", "z"],   # nulo
        ["b", "a"],        # invertido
    ]
    for ranked in test_cases:
        n = ndcg_at_k(ranked, expected, 5)
        assert 0.0 <= n <= 1.0, f"NDCG fuera de rango para {ranked}: {n}"


def test_ndcg_more_relevant_than_k() -> None:
    """Si |expected| > k, IDCG considera solo k relevantes."""
    ranked = ["a", "b"]
    expected = ["a", "b", "c", "d", "e"]
    # k=2, los 2 primeros son relevantes → DCG=DCG_ideal → 1.0
    assert ndcg_at_k(ranked, expected, 2) == 1.0
