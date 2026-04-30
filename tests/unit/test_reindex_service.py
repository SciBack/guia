"""Tests del ReindexService — pgvector → OpenSearch (M3 hotfix)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from guia.services.reindex import (
    ReindexService,
    ReindexStats,
    _IndexableRecord,
)


# ── _IndexableRecord (Indexable Protocol) ────────────────────────────────


def test_indexable_record_search_index_name() -> None:
    record = _IndexableRecord("doc-1", [0.1] * 8, {"title": "T"})
    assert record.search_index_name() == "publication"


def test_indexable_record_to_search_document() -> None:
    record = _IndexableRecord(
        "dspace:123",
        [0.1, 0.2, 0.3],
        {
            "title": "Tesis sobre IA",
            "abstract": "Estudio detallado",
            "authors": ["Pérez, J."],
            "year": 2024,
            "url": "http://repo.upeu.edu.pe/handle/123",
            "source": "dspace",
            "kind": "thesis",
            "subjects_ocde": ["1.02 Computación"],
        },
    )
    doc = record.to_search_document()

    assert doc["id"] == "dspace:123"
    assert doc["title"] == "Tesis sobre IA"
    assert doc["abstract"] == "Estudio detallado"
    assert doc["authors"] == ["Pérez, J."]
    assert doc["publication_year"] == 2024
    assert doc["external_resource_uri"] == "http://repo.upeu.edu.pe/handle/123"
    assert doc["source"] == "dspace"
    assert doc["embedding"] == [0.1, 0.2, 0.3]
    assert "vector" not in doc  # field name correcto es "embedding" (sciback-core mapping)
    assert doc["kind"] == "thesis"
    assert doc["subjects_ocde"] == ["1.02 Computación"]


def test_indexable_record_handles_missing_metadata() -> None:
    """Metadata vacía no rompe la conversión."""
    record = _IndexableRecord("x", [0.0], {})
    doc = record.to_search_document()
    assert doc["id"] == "x"
    assert doc["title"] == ""
    assert doc["abstract"] == ""
    assert doc["authors"] == []
    assert doc["source"] == "unknown"


# ── _parse_vector ────────────────────────────────────────────────────────


def test_parse_vector_standard_format() -> None:
    assert ReindexService._parse_vector("[1.0,2.0,3.0]") == [1.0, 2.0, 3.0]


def test_parse_vector_with_spaces() -> None:
    assert ReindexService._parse_vector(" [0.5, -0.3] ") == [0.5, -0.3]


def test_parse_vector_empty() -> None:
    assert ReindexService._parse_vector("[]") == []


# ── ReindexStats ─────────────────────────────────────────────────────────


def test_reindex_stats_merge() -> None:
    a = ReindexStats(total_read=10, total_indexed=8, total_failed=2)
    b = ReindexStats(total_read=5, total_indexed=5, skipped_chunks=3)
    a.merge(b)
    assert a.total_read == 15
    assert a.total_indexed == 13
    assert a.total_failed == 2
    assert a.skipped_chunks == 3


def test_reindex_stats_merge_caps_errors() -> None:
    a = ReindexStats(errors=[f"err{i}" for i in range(20)])
    b = ReindexStats(errors=["err_extra1", "err_extra2"])
    a.merge(b)
    assert len(a.errors) == 20  # cap


# ── ReindexService.reindex_all (con mocks) ──────────────────────────────


def _fake_pg_store_with_rows(rows: list[tuple[str, str, dict[str, Any]]]) -> MagicMock:
    """Construye un mock de PgVectorStore que itera filas en un solo batch."""
    store = MagicMock()
    engine = MagicMock()

    # _iter_batches usa context manager engine.connect() → conn.execute().fetchall()
    conn = MagicMock()
    # Primera llamada (sin last_id): devuelve las filas. Segunda llamada: vacío.
    fetch_iter = iter([rows, []])
    conn.execute.return_value.fetchall.side_effect = lambda: next(fetch_iter)
    # Para count_documents
    conn.execute.return_value.scalar.return_value = len(rows)

    engine.connect.return_value.__enter__.return_value = conn
    engine.connect.return_value.__exit__.return_value = False
    store._engine = engine
    return store


def _fake_os_port_success(indexed: int = 0, failed: int = 0) -> MagicMock:
    """Mock OpenSearchSearchPort.bulk_index."""
    port = MagicMock()
    result = MagicMock()
    result.indexed = indexed
    result.failed = failed
    result.errors = []
    port.bulk_index = AsyncMock(return_value=result)
    return port


@pytest.mark.asyncio
async def test_reindex_iterates_and_indexes() -> None:
    rows = [
        ("dspace:1", "[0.1,0.2]", {"title": "T1", "source": "dspace"}),
        ("dspace:2", "[0.3,0.4]", {"title": "T2", "source": "dspace"}),
    ]
    pg = _fake_pg_store_with_rows(rows)
    os_port = _fake_os_port_success(indexed=2, failed=0)

    service = ReindexService(pg_store=pg, os_port=os_port)
    stats = await service.reindex_all(batch_size=10)

    assert stats.total_read == 2
    assert stats.total_indexed == 2
    assert stats.total_failed == 0
    os_port.bulk_index.assert_called_once()


@pytest.mark.asyncio
async def test_reindex_skips_chunks_by_default() -> None:
    """Chunks (is_chunk=True) se saltan — solo padres se indexan."""
    rows = [
        ("dspace:1", "[0.1]", {"title": "Padre"}),
        ("dspace:1#chunk_0", "[0.2]", {"is_chunk": True, "parent_id": "dspace:1"}),
        ("dspace:1#chunk_1", "[0.3]", {"is_chunk": True, "parent_id": "dspace:1"}),
    ]
    pg = _fake_pg_store_with_rows(rows)
    os_port = _fake_os_port_success(indexed=1)

    service = ReindexService(pg_store=pg, os_port=os_port, skip_chunks=True)
    stats = await service.reindex_all(batch_size=10)

    assert stats.total_read == 3
    assert stats.skipped_chunks == 2
    assert stats.total_indexed == 1


@pytest.mark.asyncio
async def test_reindex_dry_run_does_not_call_bulk_index() -> None:
    rows = [
        ("dspace:1", "[0.1]", {"title": "T"}),
    ]
    pg = _fake_pg_store_with_rows(rows)
    os_port = _fake_os_port_success()

    service = ReindexService(pg_store=pg, os_port=os_port)
    stats = await service.reindex_all(batch_size=10, dry_run=True)

    assert stats.total_read == 1
    os_port.bulk_index.assert_not_called()


@pytest.mark.asyncio
async def test_reindex_handles_bulk_failures() -> None:
    rows = [("dspace:1", "[0.1]", {"title": "T"})]
    pg = _fake_pg_store_with_rows(rows)

    os_port = MagicMock()
    result = MagicMock()
    result.indexed = 0
    result.failed = 1
    result.errors = ["mapper_parsing_exception"]
    os_port.bulk_index = AsyncMock(return_value=result)

    service = ReindexService(pg_store=pg, os_port=os_port)
    stats = await service.reindex_all(batch_size=10)

    assert stats.total_failed == 1
    assert "mapper_parsing_exception" in stats.errors


@pytest.mark.asyncio
async def test_reindex_handles_exception_per_batch() -> None:
    """Si bulk_index lanza, el reindex captura y sigue."""
    rows = [("dspace:1", "[0.1]", {"title": "T"})]
    pg = _fake_pg_store_with_rows(rows)

    os_port = MagicMock()
    os_port.bulk_index = AsyncMock(side_effect=RuntimeError("connection lost"))

    service = ReindexService(pg_store=pg, os_port=os_port)
    stats = await service.reindex_all(batch_size=10)

    assert stats.total_failed == 1
    assert any("connection lost" in e for e in stats.errors)


# ── count_documents ──────────────────────────────────────────────────────


def test_count_documents_returns_total() -> None:
    pg = _fake_pg_store_with_rows([])
    # Override del scalar
    conn = pg._engine.connect.return_value.__enter__.return_value
    conn.execute.return_value.scalar.return_value = 35729

    service = ReindexService(pg_store=pg, os_port=MagicMock())
    assert service.count_documents() == 35729


def test_count_documents_handles_null() -> None:
    pg = _fake_pg_store_with_rows([])
    conn = pg._engine.connect.return_value.__enter__.return_value
    conn.execute.return_value.scalar.return_value = None

    service = ReindexService(pg_store=pg, os_port=MagicMock())
    assert service.count_documents() == 0
