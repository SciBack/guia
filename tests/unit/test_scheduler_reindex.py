"""Tests del job reindex_opensearch_job en el scheduler."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from guia.scheduler.jobs import reindex_opensearch_job


def test_reindex_skipped_when_search_backend_pgvector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si SEARCH_BACKEND=pgvector, no-op sin tocar el store."""
    from guia.scheduler import jobs

    monkeypatch.setattr(jobs._settings, "search_backend", "pgvector")
    container = MagicMock()
    container.search_adapter = MagicMock()  # debería ser ignorado

    reindex_opensearch_job(container)

    # ReindexService no se construye, search_adapter no se usa
    container.search_adapter._os.assert_not_called()


def test_reindex_skipped_when_no_search_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si search_adapter es None, log warning y no-op."""
    from guia.scheduler import jobs

    monkeypatch.setattr(jobs._settings, "search_backend", "dual")
    container = MagicMock()
    container.search_adapter = None

    # No debería lanzar excepción
    reindex_opensearch_job(container)


def test_reindex_skipped_when_store_not_pgvector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si el store no es PgVectorStore, no-op gracioso."""
    from guia.scheduler import jobs

    monkeypatch.setattr(jobs._settings, "search_backend", "dual")
    container = MagicMock()
    container.search_adapter = MagicMock()
    # MagicMock no es instancia de PgVectorStore → skip
    container.store = MagicMock(spec=object)

    reindex_opensearch_job(container)
    # No debería haber llamada de bulk_index
