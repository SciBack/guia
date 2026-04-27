"""ModelRouter — elige el LLM de síntesis según complejidad de la query.

Estrategia: cosine similarity contra centroides de ejemplos pre-embebidos.

Latencia real:
- Primer uso: ~800ms para calcular centroides (33 embed_query en thread pool).
- Consultas siguientes: <1ms (solo aritmética de vectores en memoria).

No agrega llamadas al LLM. Reutiliza el query_vector ya calculado
en ChatService.answer() — costo extra = 0.
"""

from __future__ import annotations

import asyncio
import math
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sciback_embeddings_e5 import E5EmbeddingAdapter


class QueryTier(StrEnum):
    FAST = "fast"  # qwen2.5:3b — saludo, conversación, info simple
    FULL = "full"  # qwen2.5:7b — research, RAG, razonamiento multi-paso


# ── Ejemplos por categoría ────────────────────────────────────────────────
# FAST: conversacional, saludos, info instantánea, meta-preguntas sobre GUIA
_FAST_EXAMPLES: list[str] = [
    "hola",
    "buenos días",
    "buenas tardes",
    "buenas noches",
    "gracias",
    "muchas gracias",
    "adiós",
    "hasta luego",
    "¿cómo estás?",
    "ok",
    "perfecto",
    "entendido",
    "¿en qué me puedes ayudar?",
    "¿qué puedes hacer?",
    "¿qué es GUIA?",
    "no entendí, explícame de nuevo",
    "¿puedes repetir eso?",
    "sí, continúa",
    "no, gracias",
    "¿cuándo fue fundada la UPeU?",
    "¿dónde queda la universidad?",
    "¿cuál es el teléfono de la universidad?",
]

# FULL: consultas académicas, búsquedas complejas, datos personales del SIS
_FULL_EXAMPLES: list[str] = [
    "busca tesis sobre inteligencia artificial en el repositorio",
    "¿cuáles son mis notas del semestre actual?",
    "¿tengo préstamos vencidos en la biblioteca?",
    "¿qué investigaciones publicó la Facultad de Ingeniería este año?",
    "¿en qué revistas UPeU puedo publicar mi artículo?",
    "¿cuál es mi horario completo de esta semana?",
    "¿está disponible Cálculo de Stewart en la biblioteca?",
    "¿cuál es mi promedio ponderado acumulado?",
    "¿cuántos créditos me faltan para graduarme?",
    "¿cuándo es el próximo congreso de investigación UPeU?",
    "¿cómo accedo a las bases de datos digitales de biblioteca?",
    "explícame el proceso de titulación en la UPeU",
    "resumen del reglamento de investigación de la universidad",
    "¿qué eventos hay esta semana en el salón de actos?",
    "¿en qué aula tengo el examen de mañana?",
    "¿cuándo vence el plazo de mis préstamos de biblioteca?",
    "artículos recientes sobre nutrición infantil en zonas rurales",
    "tesis de teología adventista publicadas después de 2020",
    "investigaciones sobre energías renovables en la facultad de ingeniería",
    "¿hay tesis sobre machine learning en ciencias de la salud?",
    "¿cómo citar una tesis del repositorio UPeU en formato APA?",
]


# ── Aritmética de vectores ────────────────────────────────────────────────

def _cosine(a: list[float], b: list[float]) -> float:
    """Similitud coseno entre dos vectores."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _centroid(vectors: list[list[float]]) -> list[float]:
    """Promedio aritmético de una lista de vectores (centroide)."""
    n = len(vectors)
    dim = len(vectors[0])
    return [sum(v[i] for v in vectors) / n for i in range(dim)]


# ── Router ────────────────────────────────────────────────────────────────

class ModelRouter:
    """Enruta queries al modelo adecuado usando similitud de embeddings.

    Instanciar una sola vez (en GUIAContainer). Los centroides se calculan
    de forma lazy al primer uso y quedan en memoria indefinidamente.

    Args:
        embedder: E5EmbeddingAdapter ya inicializado.
    """

    def __init__(self, embedder: E5EmbeddingAdapter) -> None:
        self._embedder = embedder
        self._fast_centroid: list[float] | None = None
        self._full_centroid: list[float] | None = None

    # ── Inicialización ────────────────────────────────────────────────────

    def _compute_centroids_sync(self) -> None:
        """Calcula centroides embebiendo todos los ejemplos (sync, en thread)."""
        fast_vecs = [self._embedder.embed_query(ex) for ex in _FAST_EXAMPLES]
        full_vecs = [self._embedder.embed_query(ex) for ex in _FULL_EXAMPLES]
        self._fast_centroid = _centroid(fast_vecs)
        self._full_centroid = _centroid(full_vecs)

    async def warm_up(self) -> None:
        """Pre-calcula los centroides en un thread pool.

        Llamar una vez al inicio (ej: @cl.on_app_startup) para que la
        primera consulta real no pague el costo de inicialización.
        """
        await asyncio.to_thread(self._compute_centroids_sync)

    @property
    def ready(self) -> bool:
        """True si los centroides ya están calculados."""
        return self._fast_centroid is not None

    # ── Routing ───────────────────────────────────────────────────────────

    def route(self, query_vector: list[float]) -> QueryTier:
        """Determina el tier del modelo para una query ya embebida.

        Reutiliza el query_vector calculado en ChatService.answer() —
        no hay ningún costo extra de red o cómputo.

        Args:
            query_vector: Embedding de la query (calculado previamente).

        Returns:
            QueryTier.FAST si la query es conversacional/simple.
            QueryTier.FULL si requiere razonamiento complejo o RAG.

        Note:
            Si los centroides no están listos (warm_up no se llamó),
            retorna FULL como fallback seguro.
        """
        if self._fast_centroid is None or self._full_centroid is None:
            return QueryTier.FULL

        sim_fast = _cosine(query_vector, self._fast_centroid)
        sim_full = _cosine(query_vector, self._full_centroid)

        return QueryTier.FAST if sim_fast > sim_full else QueryTier.FULL
