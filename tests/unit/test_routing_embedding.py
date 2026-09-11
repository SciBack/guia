"""Tests del EmbeddingRouter (Gate 2, P1.2 paso 3)."""

from __future__ import annotations

import asyncio

import pytest

from guia.routing import Gate, IntentCategory, PrivacyLevel, Tier
from guia.routing.embedding import EmbeddingRouter

# ── Fake embedder con vectores deterministas por categoría ───────────────


class FakeEmbedder:
    """Embedder que devuelve vectores fijos según keywords en la query.

    Usa una dimensión por categoría, para que cada centroide quede cerca de
    su eje:
        [campus_personal, campus_generico, research_simple, research_deep,
         institucional]

    La quinta se añadió el 11-sep-2026 con la categoría institucional. Sin
    ella, sus ejemplos no casaban con ninguna palabra del diccionario de
    abajo, así que todos se embebían al vector uniforme — y su centroide se
    convertía en el vector uniforme, que es justo el que devuelve una query
    sin sentido. Resultado: "xyzzy nonsense" clasificaba como institucional
    con similitud 0,977. El doble tiene que crecer con las categorías.
    """

    embedding_dim = 5

    _BUCKETS = {
        # campus_personal
        "mis": (1.0, 0.0, 0.0, 0.0, 0.0),
        "promedio": (1.0, 0.0, 0.0, 0.0, 0.0),
        "deuda": (1.0, 0.0, 0.0, 0.0, 0.0),
        "préstamos": (1.0, 0.0, 0.0, 0.0, 0.0),
        "horario": (1.0, 0.0, 0.0, 0.0, 0.0),
        "matrícula": (1.0, 0.0, 0.0, 0.0, 0.0),
        "créditos": (1.0, 0.0, 0.0, 0.0, 0.0),
        "biblioteca": (1.0, 0.0, 0.0, 0.0, 0.0),
        "saldo": (1.0, 0.0, 0.0, 0.0, 0.0),
        "cuenta": (1.0, 0.0, 0.0, 0.0, 0.0),
        "notas": (1.0, 0.0, 0.0, 0.0, 0.0),
        "vencidos": (1.0, 0.0, 0.0, 0.0, 0.0),
        # campus_generico
        "calendario": (0.0, 1.0, 0.0, 0.0, 0.0),
        "eventos": (0.0, 1.0, 0.0, 0.0, 0.0),
        "reglamento": (0.0, 1.0, 0.0, 0.0, 0.0),
        "becas": (0.0, 1.0, 0.0, 0.0, 0.0),
        "atención": (0.0, 1.0, 0.0, 0.0, 0.0),
        "feria": (0.0, 1.0, 0.0, 0.0, 0.0),
        "congreso": (0.0, 1.0, 0.0, 0.0, 0.0),
        "titulación": (0.0, 1.0, 0.0, 0.0, 0.0),
        "ubicación": (0.0, 1.0, 0.0, 0.0, 0.0),
        "salón": (0.0, 1.0, 0.0, 0.0, 0.0),
        # research_simple
        "tesis": (0.0, 0.0, 1.0, 0.0, 0.0),
        "artículos": (0.0, 0.0, 1.0, 0.0, 0.0),
        "libros": (0.0, 0.0, 1.0, 0.0, 0.0),
        "busca": (0.0, 0.0, 1.0, 0.0, 0.0),
        "papers": (0.0, 0.0, 1.0, 0.0, 0.0),
        "revistas": (0.0, 0.0, 1.0, 0.0, 0.0),
        "investigaciones": (0.0, 0.0, 1.0, 0.0, 0.0),
        "autor": (0.0, 0.0, 1.0, 0.0, 0.0),
        "stewart": (0.0, 0.0, 1.0, 0.0, 0.0),
        "machine": (0.0, 0.0, 1.0, 0.0, 0.0),
        "learning": (0.0, 0.0, 1.0, 0.0, 0.0),
        # research_deep
        "compara": (0.0, 0.0, 0.0, 1.0, 0.0),
        "síntesis": (0.0, 0.0, 0.0, 1.0, 0.0),
        "metodologías": (0.0, 0.0, 0.0, 1.0, 0.0),
        "marco": (0.0, 0.0, 0.0, 1.0, 0.0),
        "bibliométrico": (0.0, 0.0, 0.0, 1.0, 0.0),
        "tendencias": (0.0, 0.0, 0.0, 1.0, 0.0),
        "evolución": (0.0, 0.0, 0.0, 1.0, 0.0),
        "comparativa": (0.0, 0.0, 0.0, 1.0, 0.0),
        "estado": (0.0, 0.0, 0.0, 1.0, 0.0),
        "redes": (0.0, 0.0, 0.0, 1.0, 0.0),
        "mapeo": (0.0, 0.0, 0.0, 1.0, 0.0),
        # institucional
        "área": (0.0, 0.0, 0.0, 0.0, 1.0),
        "áreas": (0.0, 0.0, 0.0, 0.0, 1.0),
        "dti": (0.0, 0.0, 0.0, 0.0, 1.0),
        "dirección": (0.0, 0.0, 0.0, 0.0, 1.0),
        "encarga": (0.0, 0.0, 0.0, 0.0, 1.0),
        "organigrama": (0.0, 0.0, 0.0, 0.0, 1.0),
        "procesos": (0.0, 0.0, 0.0, 0.0, 1.0),
        "oficina": (0.0, 0.0, 0.0, 0.0, 1.0),
        "responsable": (0.0, 0.0, 0.0, 0.0, 1.0),
        "servicios": (0.0, 0.0, 0.0, 0.0, 1.0),
    }

    def embed_query(self, query: str) -> list[float]:
        """Suma componentes según palabras presentes.

        Las dimensiones se cuentan con ``embedding_dim`` y no con un 4 fijo:
        el literal fue lo que dejó la categoría institucional sin eje propio
        cuando se añadió.
        """
        n = self.embedding_dim
        v = [0.0] * n
        words = query.lower().split()
        for w in words:
            stripped = w.strip("¿?¡!.,;:")
            if stripped in self._BUCKETS:
                bucket = self._BUCKETS[stripped]
                v = [v[i] + bucket[i] for i in range(n)]
        # Norma mínima para evitar vector nulo
        if all(x == 0.0 for x in v):
            v = [1.0 / n] * n
        return v


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def router() -> EmbeddingRouter:
    r = EmbeddingRouter(FakeEmbedder())
    asyncio.run(r.warm_up())
    return r


# ── Estado del router ─────────────────────────────────────────────────────


def test_router_not_ready_before_warmup() -> None:
    """Sin warm_up, el router no está listo y retorna None."""
    r = EmbeddingRouter(FakeEmbedder())
    assert r.ready is False
    assert r.decide([1.0, 0.0, 0.0, 0.0]) is None


def test_router_ready_after_warmup(router: EmbeddingRouter) -> None:
    assert router.ready is True


# ── Clasificación por categoría ──────────────────────────────────────────


def test_classifies_campus_personal_as_always_local(router: EmbeddingRouter) -> None:
    embedder = FakeEmbedder()
    qv = embedder.embed_query("muéstrame mis notas y promedio")
    d = router.decide(qv)

    assert d is not None
    assert d.intent == IntentCategory.CAMPUS_PERSONAL
    assert d.privacy == PrivacyLevel.ALWAYS_LOCAL
    assert d.tier == Tier.T1_STD
    assert d.gate_used == Gate.EMBEDDING


def test_classifies_campus_generico_as_cloud_ok(router: EmbeddingRouter) -> None:
    embedder = FakeEmbedder()
    qv = embedder.embed_query("calendario académico y eventos")
    d = router.decide(qv)

    assert d is not None
    assert d.intent == IntentCategory.CAMPUS_GENERICO
    assert d.privacy == PrivacyLevel.CLOUD_OK
    assert d.tier == Tier.T0_FAST


def test_classifies_research_simple_as_t1(router: EmbeddingRouter) -> None:
    embedder = FakeEmbedder()
    qv = embedder.embed_query("busca tesis y artículos sobre machine learning")
    d = router.decide(qv)

    assert d is not None
    assert d.intent == IntentCategory.RESEARCH_SIMPLE
    assert d.tier == Tier.T1_STD
    assert d.privacy == PrivacyLevel.CLOUD_OK


def test_classifies_research_deep_as_t2(router: EmbeddingRouter) -> None:
    embedder = FakeEmbedder()
    qv = embedder.embed_query("compara metodologías y haz síntesis bibliométrico")
    d = router.decide(qv)

    assert d is not None
    assert d.intent == IntentCategory.RESEARCH_DEEP
    assert d.tier == Tier.T2_DEEP


# ── Confianza ────────────────────────────────────────────────────────────


def test_confidence_high_when_clear_winner(router: EmbeddingRouter) -> None:
    """Query alineada fuerte con un centroide → confidence alta."""
    embedder = FakeEmbedder()
    qv = embedder.embed_query("tesis artículos libros busca papers")
    d = router.decide(qv)
    assert d is not None
    assert d.confidence >= 0.5


def test_confidence_low_when_ambiguous(router: EmbeddingRouter) -> None:
    """Query equidistante de múltiples centroides → confidence baja."""
    embedder = FakeEmbedder()
    # Query sin keywords → vector uniforme [0.25, 0.25, 0.25, 0.25]
    qv = embedder.embed_query("xyzzy nonsense")
    d = router.decide(qv)
    assert d is not None
    assert d.confidence < 0.5  # ambigüedad detectable


# ── Metadata de la decisión ──────────────────────────────────────────────


def test_decision_includes_latency_and_reason(router: EmbeddingRouter) -> None:
    embedder = FakeEmbedder()
    qv = embedder.embed_query("mis notas")
    d = router.decide(qv)
    assert d is not None
    assert d.latency_ms >= 0.0
    assert "centroid" in d.reason
    assert "campus_personal" in d.reason
