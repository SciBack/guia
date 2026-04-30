"""Evaluation harness — métricas de retrieval (P3.3, roadmap-v1).

Funciones puras para calcular métricas IR estándar sobre rankings.
Usadas por:
- Tests de regresión: detectar drift en la calidad de retrieval cuando
  se cambian centroides, embedder, o estrategia de chunking.
- A/B testing: comparar variantes (con/sin full-text, k=5 vs k=10) sobre
  una suite gold-standard.

Métricas implementadas:
- ndcg_at_k(ranked, expected, k) — Normalized DCG, principal métrica IR
- recall_at_k(ranked, expected, k) — % de docs relevantes recuperados
- precision_at_k(ranked, expected, k) — % de hits que son relevantes
"""

from guia.eval.metrics import (
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)

__all__ = [
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
]
