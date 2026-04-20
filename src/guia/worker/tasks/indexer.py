"""Celery tasks — OpenSearch indexing (ADR-013 / ADR-029)."""

from __future__ import annotations

from guia.worker.celery_app import app


@app.task(
    name="guia.worker.tasks.indexer.index_publication",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    time_limit=60,
)
def index_publication(self: object, publication_id: str) -> dict:
    """Indexa una publicación en OpenSearch."""
    # Implementación completa en M2 cuando SearchPort esté conectado
    return {"indexed": publication_id, "status": "queued"}


@app.task(
    name="guia.worker.tasks.indexer.reindex_opensearch",
    bind=True,
    max_retries=1,
    acks_late=True,
    time_limit=3600,
)
def reindex_opensearch(self: object) -> dict:
    """Reconstruye índices OpenSearch completos."""
    return {"status": "reindex_started"}


@app.task(
    name="guia.worker.tasks.indexer.generate_catalog_snapshot",
    bind=True,
    max_retries=2,
    acks_late=True,
    time_limit=1800,
)
def generate_catalog_snapshot(self: object) -> dict:
    """Genera dump JSON mensual del catálogo hacia MinIO (ADR-033)."""
    # MinIO: sciback-snapshots bucket vía StoragePort (M2)
    return {"status": "snapshot_queued"}
