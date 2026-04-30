"""EmbeddingRouter — Gate 2 de la cascada (~1ms).

Reusa el query_vector ya calculado por ChatService → costo extra = 0.
Compara contra 4 centroides de categorías (no 2 como el ModelRouter legacy):

- CAMPUS_PERSONAL  → ALWAYS_LOCAL + T1_STD     (guardrail de privacidad)
- CAMPUS_GENERICO  → CLOUD_OK + T0_FAST        (calendario, eventos públicos)
- RESEARCH_SIMPLE  → CLOUD_OK + T1_STD         (catálogo, "¿hay X?")
- RESEARCH_DEEP    → CLOUD_OK + T2_DEEP        (síntesis multi-doc)

Si el margin entre top-1 y top-2 es bajo, marca confidence < umbral —
la cascada puede usar eso para activar Gate 3 (LLM classifier opt-in).
"""

from __future__ import annotations

import asyncio
import math
import time
from typing import TYPE_CHECKING

from guia.routing.decision import (
    Gate,
    IntentCategory,
    PrivacyLevel,
    RouteDecision,
    Tier,
)

if TYPE_CHECKING:
    from sciback_embeddings_e5 import E5EmbeddingAdapter


# ── Ejemplos por categoría ────────────────────────────────────────────────

_CAMPUS_PERSONAL_EXAMPLES: list[str] = [
    "muéstrame mis notas del semestre",
    "¿cuál es mi promedio acumulado?",
    "¿cuánto debo en biblioteca?",
    "estado de cuenta financiera",
    "¿tengo libros vencidos?",
    "mis préstamos activos",
    "mi horario de clases de esta semana",
    "¿cuántos créditos tengo aprobados?",
    "mi avance curricular",
    "¿cuándo vence mi pago de matrícula?",
]

_CAMPUS_GENERICO_EXAMPLES: list[str] = [
    "¿cuándo empiezan las clases del próximo semestre?",
    "calendario académico de mayo",
    "¿qué eventos hay esta semana en la universidad?",
    "horario de atención de la biblioteca",
    "ubicación del salón de actos",
    "reglamento general de estudios",
    "proceso de titulación en la UPeU",
    "¿cómo me inscribo a un congreso UPeU?",
    "becas disponibles este año",
    "fecha de feria de investigación",
]

_RESEARCH_SIMPLE_EXAMPLES: list[str] = [
    "¿hay tesis sobre machine learning?",
    "¿está disponible Cálculo de Stewart en biblioteca?",
    "busca artículos sobre educación virtual",
    "¿qué libros hay sobre teología sistemática?",
    "tesis publicadas en 2023",
    "artículos sobre nutrición infantil",
    "lista de revistas UPeU indexadas",
    "¿hay investigaciones sobre energías renovables?",
    "busca por autor Pérez García",
    "papers sobre IA en educación superior",
]

_RESEARCH_DEEP_EXAMPLES: list[str] = [
    "compara metodologías de tesis sobre IA en salud entre 2020 y 2024",
    "síntesis crítica de investigaciones sobre teología adventista de los últimos 10 años",
    "análisis bibliométrico de la producción científica de la facultad de ingeniería",
    "estructura un marco teórico sobre depresión en adolescentes peruanos",
    "evolución de los temas de investigación en nutrición pública UPeU",
    "qué tendencias hay en tesis de educación virtual post-pandemia",
    "comparativa entre métodos cuantitativos y cualitativos en tesis de psicología UPeU",
    "redes de colaboración entre autores en repositorio institucional",
    "mapeo conceptual de tesis sobre cambio climático en LATAM",
    "elabora un estado del arte sobre gamificación en educación universitaria",
]


_CATEGORY_SPEC: dict[IntentCategory, tuple[list[str], Tier, PrivacyLevel]] = {
    IntentCategory.CAMPUS_PERSONAL: (_CAMPUS_PERSONAL_EXAMPLES, Tier.T1_STD, PrivacyLevel.ALWAYS_LOCAL),
    IntentCategory.CAMPUS_GENERICO: (_CAMPUS_GENERICO_EXAMPLES, Tier.T0_FAST, PrivacyLevel.CLOUD_OK),
    IntentCategory.RESEARCH_SIMPLE: (_RESEARCH_SIMPLE_EXAMPLES, Tier.T1_STD, PrivacyLevel.CLOUD_OK),
    IntentCategory.RESEARCH_DEEP: (_RESEARCH_DEEP_EXAMPLES, Tier.T2_DEEP, PrivacyLevel.CLOUD_OK),
}


# ── Aritmética de vectores ────────────────────────────────────────────────


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _centroid(vectors: list[list[float]]) -> list[float]:
    n = len(vectors)
    dim = len(vectors[0])
    return [sum(v[i] for v in vectors) / n for i in range(dim)]


# ── Router ────────────────────────────────────────────────────────────────


class EmbeddingRouter:
    """Gate 2 — clasifica por similitud coseno contra 4 centroides.

    Latencia <1ms una vez warm. Reutiliza query_vector ya calculado.

    Args:
        embedder: E5EmbeddingAdapter para calcular centroides al warm_up.
    """

    def __init__(self, embedder: E5EmbeddingAdapter) -> None:
        self._embedder = embedder
        self._centroids: dict[IntentCategory, list[float]] = {}

    @property
    def ready(self) -> bool:
        """True si los 4 centroides ya están calculados."""
        return len(self._centroids) == len(_CATEGORY_SPEC)

    def _compute_centroids_sync(self) -> None:
        for cat, (examples, _tier, _privacy) in _CATEGORY_SPEC.items():
            vecs = [self._embedder.embed_query(ex) for ex in examples]
            self._centroids[cat] = _centroid(vecs)

    async def warm_up(self) -> None:
        """Pre-calcula los 4 centroides en thread pool."""
        await asyncio.to_thread(self._compute_centroids_sync)

    def decide(self, query_vector: list[float]) -> RouteDecision | None:
        """Retorna RouteDecision o None si no está warm.

        El caller (CascadeRouter) decide qué hacer con confidence baja
        (típicamente: pasar a Gate 3 si margin < 0.05).
        """
        if not self.ready:
            return None

        t0 = time.perf_counter()
        sims = {cat: _cosine(query_vector, c) for cat, c in self._centroids.items()}
        ranked = sorted(sims.items(), key=lambda kv: kv[1], reverse=True)

        top_cat, top_sim = ranked[0]
        runner_sim = ranked[1][1]
        margin = top_sim - runner_sim

        # confidence: 1.0 con margin grande, baja cuando los top-2 están cerca
        confidence = min(1.0, max(0.0, margin / 0.10))  # margin>=0.10 → confidence=1

        _examples, tier, privacy = _CATEGORY_SPEC[top_cat]
        latency_ms = (time.perf_counter() - t0) * 1000

        return RouteDecision(
            intent=top_cat,
            tier=tier,
            privacy=privacy,
            gate_used=Gate.EMBEDDING,
            confidence=confidence,
            latency_ms=latency_ms,
            reason=f"centroid:{top_cat.value} sim={top_sim:.3f} margin={margin:.3f}",
        )
