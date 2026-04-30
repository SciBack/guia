"""Harness A/B para evaluar retrieval quality con NDCG@5 (P3.3).

Construye dos índices in-memory equivalentes:
- A) "abstract-only": cada doc indexado solo con title + abstract (corto)
- B) "full-text": además, chunks indexados con parent_id apuntando al doc

Para cada query del gold-standard, ejecuta el retrieval en ambos modos y
calcula NDCG@5. Reporta promedio + delta entre modos.

Uso del FakeEmbedder determinístico permite que la métrica sea estable y
reproducible en CI — en producción los números cambian con el embedder
real (multilingual-e5-large) pero la estructura de la métrica es la misma.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sciback_core.ports.vector_store import (
    InMemoryVectorStoreAdapter,
    VectorRecord,
)

from guia.eval.metrics import ndcg_at_k, precision_at_k, recall_at_k
from guia.services.chunking import iter_chunks_for_publication
from guia.services.search import SearchService


# ── Pseudo-corpus para tests deterministas ────────────────────────────────


@dataclass(frozen=True)
class CorpusDoc:
    """Documento del pseudo-corpus para evaluación."""

    doc_id: str
    title: str
    abstract: str
    body: str = ""  # full-text post-GROBID, solo en modo B


def _make_corpus() -> list[CorpusDoc]:
    """Pseudo-corpus de 8 docs con palabras-clave deterministas.

    Cada doc tiene:
    - title: 1-2 keywords del tema principal
    - abstract: keywords adicionales relevantes
    - body: keywords que NO están ni en title ni en abstract
            (sirve para mostrar que full-text mejora retrieval)
    """
    return [
        CorpusDoc(
            doc_id="doc-ai-edu",
            title="Inteligencia artificial en educación superior",
            abstract="Aplicaciones de IA en universidades peruanas",
            body="machine learning aulas estudiantes algoritmos",
        ),
        CorpusDoc(
            doc_id="doc-nlp-edu",
            title="Procesamiento de lenguaje natural en educación",
            abstract="NLP aplicado a tesis de inteligencia artificial",
            body="transformers BERT educación virtual",
        ),
        CorpusDoc(
            doc_id="doc-ml-aulas",
            title="Machine learning en aulas inteligentes",
            abstract="IA en educación primaria y secundaria",
            body="redes neuronales clasificación",
        ),
        CorpusDoc(
            doc_id="doc-quant-social",
            title="Estudio de variables sociales",
            abstract="Análisis cuantitativo en investigación social peruana",
            body="encuestas regresión métodos estadísticos",
        ),
        CorpusDoc(
            doc_id="doc-mixto-stats",
            title="Investigación con métodos mixtos",
            abstract="Combinación de estadística y entrevistas cualitativas",
            body="ANOVA chi cuadrado análisis cuantitativo",
        ),
        CorpusDoc(
            doc_id="doc-blockchain-fin",
            title="Blockchain en sector financiero",
            abstract="Criptomonedas y sistemas bancarios",
            body="bitcoin ethereum tokens financiero descentralizado",
        ),
        CorpusDoc(
            doc_id="doc-psico-adolesc",
            title="Depresión en adolescentes",
            abstract="Psicología clínica de jóvenes peruanos",
            body="ansiedad terapia cognitiva conductual",
        ),
        CorpusDoc(
            doc_id="doc-clinica-jovenes",
            title="Clínica juvenil y salud mental",
            abstract="Atención psicológica a jóvenes con depresión",
            body="trastornos del ánimo adolescentes evaluación",
        ),
        CorpusDoc(
            doc_id="doc-solar-pv",
            title="Energía solar fotovoltaica",
            abstract="Sistemas de energías renovables en Perú",
            body="paneles solares conversión eficiencia",
        ),
        CorpusDoc(
            doc_id="doc-eolica-mix",
            title="Energía eólica en zonas costeras",
            abstract="Aerogeneradores y energías alternativas",
            body="viento turbinas potencia renovables",
        ),
    ]


# ── FakeEmbedder con vectores word-bag ────────────────────────────────────


class WordBagEmbedder:
    """Embedder determinístico tipo TF: cada palabra única → dimensión propia.

    No es realista pero es estable y suficiente para validar que el
    pipeline de retrieval funciona. NDCG calculado con este embedder es
    una métrica de regresión interna, NO un benchmark de calidad real.
    """

    def __init__(self) -> None:
        self._vocab: dict[str, int] = {}

    @property
    def embedding_dim(self) -> int:
        # Vocab abierto: las dimensiones se descubren al ir embebiendo
        return max(len(self._vocab), 64)

    def _vec(self, text: str, dim: int) -> list[float]:
        v = [0.0] * dim
        for word in text.lower().split():
            stripped = word.strip(".,;:¿?¡!()[]")
            if not stripped:
                continue
            if stripped not in self._vocab and len(self._vocab) < dim:
                self._vocab[stripped] = len(self._vocab)
            idx = self._vocab.get(stripped)
            if idx is not None and idx < dim:
                v[idx] += 1.0
        return v

    def embed_query(self, query: str) -> list[float]:
        return self._vec(query, dim=64)

    def embed_passages(self, texts: list[str]) -> object:
        from sciback_core.ports.llm import EmbeddingResponse

        return EmbeddingResponse(
            embeddings=[self._vec(t, dim=64) for t in texts],
            model="word-bag",
            input_tokens=sum(len(t.split()) for t in texts),
        )


# ── Index builders ────────────────────────────────────────────────────────


def build_abstract_only_index(
    corpus: list[CorpusDoc], embedder: WordBagEmbedder
) -> InMemoryVectorStoreAdapter:
    """Modo A: solo title + abstract (lo que existe HOY antes de P3.1)."""
    store = InMemoryVectorStoreAdapter(dim=64)
    for doc in corpus:
        text = f"{doc.title} {doc.abstract}"
        vec = embedder._vec(text, dim=64)
        store.upsert(
            doc.doc_id,
            vec,
            metadata={"title": doc.title, "abstract": doc.abstract},
        )
    return store


def build_full_text_index(
    corpus: list[CorpusDoc], embedder: WordBagEmbedder
) -> InMemoryVectorStoreAdapter:
    """Modo B: padre con title+abstract + chunks del body (P3.1 + P3.2 simulado)."""
    store = InMemoryVectorStoreAdapter(dim=64)
    for doc in corpus:
        # Padre: solo title+abstract
        parent_text = f"{doc.title} {doc.abstract}"
        parent_vec = embedder._vec(parent_text, dim=64)
        store.upsert(
            doc.doc_id,
            parent_vec,
            metadata={
                "title": doc.title,
                "abstract": doc.abstract,
                "is_chunk": False,
            },
        )

        # Chunks: full-text post-GROBID (body)
        full_text = f"{doc.title} {doc.abstract} {doc.body}"
        chunks_iter = iter_chunks_for_publication(
            doc.doc_id,
            full_text,
            {"title": doc.title, "source": "test"},
            max_words=10,  # forzar chunking incluso en docs cortos
            overlap=2,
        )
        for cid, ctext, cmeta in chunks_iter:
            cvec = embedder._vec(ctext, dim=64)
            store.upsert(cid, cvec, metadata=cmeta)
    return store


# ── Evaluación ────────────────────────────────────────────────────────────


@dataclass
class EvalResult:
    """Resultado de evaluar la suite gold-standard contra un índice."""

    mode: str
    ndcg_per_query: dict[str, float] = field(default_factory=dict)
    recall_per_query: dict[str, float] = field(default_factory=dict)
    precision_per_query: dict[str, float] = field(default_factory=dict)

    @property
    def avg_ndcg(self) -> float:
        if not self.ndcg_per_query:
            return 0.0
        return sum(self.ndcg_per_query.values()) / len(self.ndcg_per_query)

    @property
    def avg_recall(self) -> float:
        if not self.recall_per_query:
            return 0.0
        return sum(self.recall_per_query.values()) / len(self.recall_per_query)


def load_gold_queries(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def evaluate_index(
    store: InMemoryVectorStoreAdapter,
    embedder: WordBagEmbedder,
    queries: list[dict],
    *,
    mode_label: str,
    k: int = 5,
    dedupe_chunks: bool = True,
) -> EvalResult:
    """Corre la suite contra un índice y produce EvalResult."""
    service = SearchService(store, embedder, dedupe_chunks=dedupe_chunks)  # type: ignore[arg-type]
    result = EvalResult(mode=mode_label)

    for q in queries:
        query = q["query"]
        expected = q["expected"]
        hits = service.search(query, limit=k)
        ranked_ids = [h.id for h in hits]

        result.ndcg_per_query[query] = ndcg_at_k(ranked_ids, expected, k)
        result.recall_per_query[query] = recall_at_k(ranked_ids, expected, k)
        result.precision_per_query[query] = precision_at_k(ranked_ids, expected, k)

    return result
