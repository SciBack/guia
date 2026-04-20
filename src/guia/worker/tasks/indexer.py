"""Celery tasks — OpenSearch indexing (ADR-013 / ADR-029)."""

from __future__ import annotations

import logging

from guia.worker.celery_app import app

logger = logging.getLogger(__name__)


@app.task(
    name="guia.worker.tasks.indexer.index_publication",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    time_limit=60,
)
def index_publication(self: object, publication_id: str, pub_data: dict | None = None) -> dict:
    """Indexa una publicación en OpenSearch.

    Args:
        publication_id: ID único de la publicación (mismo que en pgvector).
        pub_data: Metadatos de la publicación (title, abstract, authors, etc.).
                  Si es None, no hay nada que indexar (la publicación no tiene datos).

    M3: recibe pub_data directamente del harvester. En M4, leer de un store
    intermedio (outbox pattern) para mayor resiliencia.
    """
    from guia.config import GUIASettings
    from guia.container import GUIAContainer

    settings = GUIASettings(_env_file=None)

    if settings.search_backend == "pgvector":
        # Solo pgvector — no hay OpenSearch que indexar
        return {"indexed": publication_id, "status": "skipped_pgvector_only"}

    if pub_data is None:
        logger.warning("index_publication_no_data", pub_id=publication_id)
        return {"indexed": publication_id, "status": "skipped_no_data"}

    container = GUIAContainer(settings)
    try:
        if container.search_adapter is None:
            return {"indexed": publication_id, "status": "skipped_no_adapter"}

        # Construir objeto compatible con OpenSearchSearchPort.index()
        # El port espera un objeto con atributos id + source dict
        entity = _PublicationEntity(publication_id, pub_data)
        container.search_adapter.index_sync(entity)

        logger.info("index_publication_ok", pub_id=publication_id)
        return {"indexed": publication_id, "status": "ok"}
    except Exception as exc:
        logger.error("index_publication_error", pub_id=publication_id, exc=str(exc))
        raise self.retry(exc=exc) from exc  # type: ignore[union-attr]
    finally:
        container.close()


class _PublicationEntity:
    """Adaptador mínimo para pasar datos de publicación a OpenSearchSearchPort.index().

    OpenSearchSearchPort.index() espera un objeto con:
    - .id (str): identificador único
    - .title (str): título
    - .abstract (str): resumen
    - .authors (list[str]): autores
    - .publication_year (int | None): año
    - .external_resource_uri (str | None): URL canónica
    - .source (str): fuente de datos (dspace, ojs, alicia)
    - .vector (list[float] | None): embedding pre-calculado
    """

    def __init__(self, pub_id: str, data: dict) -> None:
        self.id = pub_id
        self.title = str(data.get("title", ""))
        self.abstract = str(data.get("abstract", ""))
        self.authors = data.get("authors", [])
        self.publication_year = data.get("year")
        self.external_resource_uri = data.get("url")
        self.source = str(data.get("source", "unknown"))
        self.vector = data.get("vector")
        self._raw = data

    def __repr__(self) -> str:
        return f"<_PublicationEntity id={self.id!r}>"


@app.task(
    name="guia.worker.tasks.indexer.reindex_opensearch",
    bind=True,
    max_retries=1,
    acks_late=True,
    time_limit=3600,
)
def reindex_opensearch(self: object) -> dict:
    """Reconstruye índices OpenSearch completos desde pgvector.

    M3: placeholder. M4 implementar iteración sobre pgvector + batch index.
    """
    # TODO M4: iterar store.list_all() → batch index_publication tasks
    return {"status": "reindex_not_implemented_until_m4"}


@app.task(
    name="guia.worker.tasks.indexer.generate_catalog_snapshot",
    bind=True,
    max_retries=2,
    acks_late=True,
    time_limit=1800,
)
def generate_catalog_snapshot(self: object) -> dict:
    """Genera dump JSON mensual del catálogo hacia MinIO (ADR-033).

    M3: placeholder. M4 implementar con StoragePort (sciback-storage-s3).
    """
    # TODO M4: pg_dump metadata → S3 bucket via StoragePort
    return {"status": "snapshot_not_implemented_until_m4"}
