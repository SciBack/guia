"""Tests de dedupe_by_parent en SearchService (P3.1)."""

from __future__ import annotations

from sciback_core.ports.vector_store import (
    InMemoryVectorStoreAdapter,
    VectorRecord,
)

from guia.services.search import SearchService, dedupe_by_parent


def _record(id_: str, score: float, **meta: object) -> VectorRecord:
    return VectorRecord(
        id=id_,
        vector=[0.0] * 8,
        metadata=dict(meta),
        score=score,
    )


# ── dedupe_by_parent stand-alone ──────────────────────────────────────────


def test_dedupe_no_chunks_returns_input() -> None:
    """Sin chunks (todos parents directos), no hay deduplicación."""
    store = InMemoryVectorStoreAdapter(dim=8)
    hits = [
        _record("pub-1", 0.9, title="A"),
        _record("pub-2", 0.7, title="B"),
    ]
    out = dedupe_by_parent(hits, store)
    assert len(out) == 2
    assert out[0].id == "pub-1"
    assert out[1].id == "pub-2"


def test_dedupe_collapses_chunks_to_parent() -> None:
    """3 chunks de un mismo parent + el parent → 1 resultado (parent)."""
    store = InMemoryVectorStoreAdapter(dim=8)
    store.upsert("pub-1", [0.0] * 8, metadata={"title": "Tesis X"})

    hits = [
        _record(
            "pub-1#chunk_0", 0.95, parent_id="pub-1", chunk_index=0, is_chunk=True
        ),
        _record("pub-1", 0.80, title="Tesis X"),  # padre
        _record(
            "pub-1#chunk_2", 0.70, parent_id="pub-1", chunk_index=2, is_chunk=True
        ),
    ]
    out = dedupe_by_parent(hits, store)
    assert len(out) == 1
    assert out[0].id == "pub-1"
    # Score reflejado: max(0.95, 0.80, 0.70) = 0.95
    assert out[0].score == 0.95


def test_dedupe_fetches_parent_when_only_chunks_in_hits() -> None:
    """Solo chunks (sin padre en hits) → recupera el padre del store."""
    store = InMemoryVectorStoreAdapter(dim=8)
    store.upsert("pub-1", [0.0] * 8, metadata={"title": "Padre completo"})

    hits = [
        _record(
            "pub-1#chunk_0", 0.85, parent_id="pub-1", chunk_index=0, is_chunk=True
        ),
        _record(
            "pub-1#chunk_1", 0.75, parent_id="pub-1", chunk_index=1, is_chunk=True
        ),
    ]
    out = dedupe_by_parent(hits, store)
    assert len(out) == 1
    assert out[0].id == "pub-1"
    assert out[0].metadata.get("title") == "Padre completo"
    assert out[0].score == 0.85  # max de los chunks


def test_dedupe_multiple_parents() -> None:
    """Hits de varios parents distintos: cada uno aparece una vez."""
    store = InMemoryVectorStoreAdapter(dim=8)
    store.upsert("pub-1", [0.0] * 8, metadata={"title": "A"})
    store.upsert("pub-2", [0.0] * 8, metadata={"title": "B"})

    hits = [
        _record("pub-1#chunk_0", 0.9, parent_id="pub-1", is_chunk=True),
        _record("pub-2#chunk_0", 0.8, parent_id="pub-2", is_chunk=True),
        _record("pub-1#chunk_1", 0.7, parent_id="pub-1", is_chunk=True),
    ]
    out = dedupe_by_parent(hits, store)
    assert len(out) == 2
    ids = [r.id for r in out]
    assert "pub-1" in ids
    assert "pub-2" in ids


def test_dedupe_preserves_order_of_first_appearance() -> None:
    """El orden del resultado sigue la primera aparición de cada grupo."""
    store = InMemoryVectorStoreAdapter(dim=8)
    store.upsert("A", [0.0] * 8, metadata={})
    store.upsert("B", [0.0] * 8, metadata={})

    hits = [
        _record("A#chunk_0", 0.5, parent_id="A", is_chunk=True),
        _record("B#chunk_0", 0.6, parent_id="B", is_chunk=True),
        _record("A#chunk_1", 0.9, parent_id="A", is_chunk=True),
    ]
    out = dedupe_by_parent(hits, store)
    assert [r.id for r in out] == ["A", "B"]


# ── SearchService.search() con dedupe ─────────────────────────────────────


class FakeEmbedder:
    embedding_dim = 8

    def embed_query(self, query: str) -> list[float]:
        return [0.5] * 8


def test_search_service_dedupes_by_default() -> None:
    """SearchService.search() aplica dedupe_by_parent por default."""
    store = InMemoryVectorStoreAdapter(dim=8)
    # Padre + 2 chunks
    store.upsert("pub-1", [1.0] * 8, metadata={"title": "Tesis"})
    store.upsert(
        "pub-1#chunk_0",
        [0.95] * 8,
        metadata={"parent_id": "pub-1", "chunk_index": 0, "is_chunk": True},
    )
    store.upsert(
        "pub-1#chunk_1",
        [0.90] * 8,
        metadata={"parent_id": "pub-1", "chunk_index": 1, "is_chunk": True},
    )

    service = SearchService(store, FakeEmbedder())  # type: ignore[arg-type]
    results = service.search("query", limit=5)

    # 1 resultado (todos del mismo parent)
    assert len(results) == 1
    assert results[0].id == "pub-1"


def test_search_service_dedupe_disabled() -> None:
    """Con dedupe_chunks=False, los chunks se devuelven sin colapsar."""
    store = InMemoryVectorStoreAdapter(dim=8)
    store.upsert("pub-1", [1.0] * 8, metadata={"title": "T"})
    store.upsert(
        "pub-1#chunk_0",
        [0.95] * 8,
        metadata={"parent_id": "pub-1", "chunk_index": 0, "is_chunk": True},
    )

    service = SearchService(store, FakeEmbedder(), dedupe_chunks=False)  # type: ignore[arg-type]
    results = service.search("query", limit=5)
    assert len(results) >= 2
