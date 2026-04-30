"""Métricas IR estándar para evaluación de retrieval (P3.3).

Implementaciones puras (sin dependencias externas) sobre listas de IDs.
Las relevancias se modelan binarias (∈{0,1}) para simplicidad — graded
relevance se puede agregar después si la suite gold-standard la requiere.
"""

from __future__ import annotations

import math


def _binary_relevance(ranked: list[str], expected: set[str]) -> list[int]:
    """Convierte (ranked_ids, expected_set) → vector de relevancias binarias."""
    return [1 if doc_id in expected else 0 for doc_id in ranked]


def precision_at_k(ranked: list[str], expected: list[str] | set[str], k: int) -> float:
    """Precision@k: hits relevantes en top-k / k.

    Args:
        ranked: IDs en orden descendente de score.
        expected: IDs relevantes (gold-standard).
        k: Cutoff.

    Returns:
        Precision en [0, 1]. Si k=0 → 0.
    """
    if k <= 0:
        return 0.0
    expected_set = set(expected)
    top_k = ranked[:k]
    hits = sum(1 for doc_id in top_k if doc_id in expected_set)
    return hits / k


def recall_at_k(ranked: list[str], expected: list[str] | set[str], k: int) -> float:
    """Recall@k: hits relevantes en top-k / total relevantes.

    Si no hay docs relevantes en expected, retorna 0 (no NaN).
    """
    expected_set = set(expected)
    if not expected_set:
        return 0.0
    top_k = ranked[:k]
    hits = sum(1 for doc_id in top_k if doc_id in expected_set)
    return hits / len(expected_set)


def dcg_at_k(relevances: list[int], k: int) -> float:
    """Discounted Cumulative Gain @ k. Fórmula estándar:

        DCG@k = Σ rel_i / log2(i + 2)   para i = 0..k-1
    """
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(relevances[:k]))


def ndcg_at_k(
    ranked: list[str], expected: list[str] | set[str], k: int
) -> float:
    """Normalized DCG @ k.

    NDCG@k = DCG@k(actual) / DCG@k(ideal). Rango [0, 1].

    Para relevancia binaria, IDCG@k es DCG sobre min(k, |expected|) unos.
    Si no hay docs relevantes, retorna 0 (convención).

    Args:
        ranked: IDs en orden descendente de score (resultado del retrieval).
        expected: IDs gold-standard relevantes.
        k: Cutoff.

    Returns:
        NDCG en [0, 1].
    """
    if k <= 0:
        return 0.0

    expected_set = set(expected)
    if not expected_set:
        return 0.0

    actual_rels = _binary_relevance(ranked, expected_set)
    dcg = dcg_at_k(actual_rels, k)

    # Ideal: todos los relevantes en el top, hasta k posiciones
    ideal_count = min(k, len(expected_set))
    ideal_rels = [1] * ideal_count + [0] * (k - ideal_count)
    idcg = dcg_at_k(ideal_rels, k)

    return dcg / idcg if idcg > 0 else 0.0
