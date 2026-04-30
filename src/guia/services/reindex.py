"""ReindexService — itera pgvector y escribe a OpenSearch (M3 hotfix).

Reemplaza al placeholder `reindex_opensearch` (Celery task M4) con un flujo
síncrono ejecutable desde CLI: `python -m guia.cli reindex --target opensearch`.

Razón de existir:
- El harvester actual escribe SOLO a pgvector (VectorStorePort.upsert).
- Los celery workers de indexación no están desplegados en UPeU.
- Sin esto, modo `SEARCH_BACKEND=dual` queda con OpenSearch vacío y el
  fallback a pgvector cubre las queries — pero no hay validación real
  de OpenSearch en producción.

Diseño:
- Cursor SQL directo sobre la tabla `sciback_vectors` con paginación por
  `created_at, id` (estable, idempotente, soporta resume con --start-after).
- Por cada batch, construir _IndexableRecord (cumple Protocol Indexable)
  y llamar a `OpenSearchSearchPort.bulk_index()`.
- Reporta `ReindexStats` con conteos + errores.
- Idempotente: ejecutar dos veces sobrescribe los mismos docs en OS
  (por `_id` igual al `id` del VectorRecord).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sciback_search_opensearch import OpenSearchSearchPort
    from sciback_vectorstore_pgvector import PgVectorStore

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 100


@dataclass
class ReindexStats:
    """Estadísticas del proceso de reindex."""

    total_read: int = 0
    """Documentos leídos de pgvector."""
    total_indexed: int = 0
    """Documentos indexados con éxito en OpenSearch."""
    total_failed: int = 0
    """Documentos que fallaron al indexar."""
    errors: list[str] = field(default_factory=list)
    """Mensajes de error (truncados a primeros 20)."""
    skipped_chunks: int = 0
    """Chunks (is_chunk=True) que se saltaron — solo padres se indexan en OS."""

    def merge(self, other: ReindexStats) -> None:
        self.total_read += other.total_read
        self.total_indexed += other.total_indexed
        self.total_failed += other.total_failed
        self.skipped_chunks += other.skipped_chunks
        if len(self.errors) < 20:
            self.errors.extend(other.errors[: 20 - len(self.errors)])


class _IndexableRecord:
    """Adaptador VectorRecord → Indexable (mismo shape que worker/_PublicationEntity).

    OpenSearchSearchPort.bulk_index() espera entities que cumplan el
    Protocol Indexable (to_search_document + search_index_name).
    """

    def __init__(self, doc_id: str, vector: list[float], metadata: dict[str, Any]) -> None:
        self._id = doc_id
        self._vector = vector
        self._meta = metadata

    def search_index_name(self) -> str:
        return "publication"

    def to_search_document(self) -> dict[str, Any]:
        return {
            "id": self._id,
            "title": str(self._meta.get("title", "")),
            "abstract": str(self._meta.get("abstract", "")),
            "authors": self._meta.get("authors", []),
            "publication_year": self._meta.get("year"),
            "external_resource_uri": self._meta.get("url"),
            "source": str(self._meta.get("source", "unknown")),
            # Campo del mapping sciback-core es "embedding" (no "vector")
            "embedding": self._vector,
            # Metadata adicional útil para filters
            "kind": self._meta.get("kind"),
            "language": self._meta.get("language"),
            "subjects": self._meta.get("subjects", []),
            "subjects_ocde": self._meta.get("subjects_ocde", []),
        }


class ReindexService:
    """Servicio de reindexación pgvector → OpenSearch.

    Args:
        pg_store: Instancia concreta de PgVectorStore (necesita acceso al
            engine SQLAlchemy para iteración eficiente).
        os_port: OpenSearchSearchPort async.
        skip_chunks: Si True, NO reindexa documentos con metadata.is_chunk=True
            (default). Los chunks no aportan a search BM25 + k-NN si el padre
            ya está indexado, y duplican volumen. Default True.
    """

    def __init__(
        self,
        pg_store: PgVectorStore,
        os_port: OpenSearchSearchPort,
        *,
        skip_chunks: bool = True,
    ) -> None:
        self._pg = pg_store
        self._os = os_port
        self._skip_chunks = skip_chunks

    def count_documents(self) -> int:
        """Cuenta total de documentos en pgvector."""
        from sqlalchemy import text

        with self._pg._engine.connect() as conn:  # type: ignore[attr-defined]
            result = conn.execute(
                text("SELECT COUNT(*) FROM sciback_vectors")
            ).scalar()
            return int(result or 0)

    async def setup_index_publication(self, embedding_dim: int = 1024) -> None:
        """Borra y crea el index 'publication' con mapping knn correcto.

        Workaround: el rebuild_index() de sciback-search-opensearch v0.x no
        habilita `index.knn=true` en settings, sin lo cual OpenSearch rechaza
        el field knn_vector con mapper_parsing_exception. Aquí aplicamos el
        mapping correcto directamente vía cliente de bajo nivel.
        """
        from opensearchpy.exceptions import NotFoundError

        client = self._os._client  # type: ignore[attr-defined]
        index_name = self._os._index_name("publication")  # type: ignore[attr-defined]

        try:
            await client.indices.delete(index=index_name)
        except NotFoundError:
            pass

        body = {
            "settings": {
                "index": {"knn": True},
                "analysis": {
                    "analyzer": {"spanish_custom": {"type": "spanish"}}
                },
            },
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "title": {
                        "type": "text",
                        "analyzer": "spanish_custom",
                        "fields": {"keyword": {"type": "keyword"}},
                    },
                    "abstract": {"type": "text", "analyzer": "spanish_custom"},
                    "authors": {"type": "keyword"},
                    "publication_year": {"type": "integer"},
                    "language": {"type": "keyword"},
                    "source": {"type": "keyword"},
                    "kind": {"type": "keyword"},
                    "external_resource_uri": {"type": "keyword"},
                    "subjects": {"type": "keyword"},
                    "subjects_ocde": {"type": "keyword"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": embedding_dim,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "lucene",
                        },
                    },
                }
            },
        }
        await client.indices.create(index=index_name, body=body)

    def _iter_batches(self, batch_size: int) -> Any:
        """Generator que produce batches de filas de pgvector ordenadas por id.

        Usa keyset pagination (cursor por id) — estable bajo updates concurrentes
        y no se degrada con OFFSET grandes.
        """
        from sqlalchemy import text

        last_id: str | None = None
        while True:
            with self._pg._engine.connect() as conn:  # type: ignore[attr-defined]
                if last_id is None:
                    rows = conn.execute(
                        text(
                            "SELECT id, vector::text, metadata FROM sciback_vectors "
                            "ORDER BY id LIMIT :limit"
                        ),
                        {"limit": batch_size},
                    ).fetchall()
                else:
                    rows = conn.execute(
                        text(
                            "SELECT id, vector::text, metadata FROM sciback_vectors "
                            "WHERE id > :last ORDER BY id LIMIT :limit"
                        ),
                        {"last": last_id, "limit": batch_size},
                    ).fetchall()

            if not rows:
                break

            yield rows
            last_id = rows[-1][0]

    @staticmethod
    def _parse_vector(raw: str) -> list[float]:
        """Convierte el texto pgvector '[1.0,2.0,...]' a list[float]."""
        # pgvector::text devuelve formato '[1,2,3,...]'
        s = raw.strip()
        if s.startswith("[") and s.endswith("]"):
            s = s[1:-1]
        if not s:
            return []
        return [float(x) for x in s.split(",")]

    async def reindex_all(
        self,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        dry_run: bool = False,
        progress_every: int = 500,
    ) -> ReindexStats:
        """Itera pgvector y reindexa cada doc en OpenSearch.

        Args:
            batch_size: Documentos por batch SQL + bulk_index.
            dry_run: Si True, NO escribe a OpenSearch — solo cuenta.
            progress_every: Loguear progreso cada N docs.

        Returns:
            ReindexStats con totales y errores.
        """
        stats = ReindexStats()
        total_count = self.count_documents()
        logger.info(
            "reindex_start",
            extra={
                "total": total_count,
                "batch_size": batch_size,
                "dry_run": dry_run,
            },
        )

        for batch_rows in self._iter_batches(batch_size):
            entities: list[_IndexableRecord] = []
            for row in batch_rows:
                doc_id = row[0]
                vector = self._parse_vector(row[1])
                metadata = row[2] if isinstance(row[2], dict) else {}
                stats.total_read += 1

                if self._skip_chunks and metadata.get("is_chunk", False):
                    stats.skipped_chunks += 1
                    continue

                entities.append(_IndexableRecord(doc_id, vector, metadata))

            if not entities or dry_run:
                if stats.total_read % progress_every == 0:
                    logger.info(
                        "reindex_progress",
                        extra={
                            "read": stats.total_read,
                            "indexed": stats.total_indexed,
                            "skipped_chunks": stats.skipped_chunks,
                        },
                    )
                continue

            try:
                result = await self._os.bulk_index(entities)
                stats.total_indexed += result.indexed
                stats.total_failed += result.failed
                if result.errors and len(stats.errors) < 20:
                    stats.errors.extend(result.errors[: 20 - len(stats.errors)])
            except Exception as exc:
                stats.total_failed += len(entities)
                msg = f"batch_error: {exc}"
                if len(stats.errors) < 20:
                    stats.errors.append(msg)
                logger.exception("reindex_batch_failed")

            if stats.total_read % progress_every < batch_size:
                logger.info(
                    "reindex_progress",
                    extra={
                        "read": stats.total_read,
                        "indexed": stats.total_indexed,
                        "failed": stats.total_failed,
                        "skipped_chunks": stats.skipped_chunks,
                    },
                )

        logger.info(
            "reindex_complete",
            extra={
                "total_read": stats.total_read,
                "total_indexed": stats.total_indexed,
                "total_failed": stats.total_failed,
                "skipped_chunks": stats.skipped_chunks,
                "errors_count": len(stats.errors),
            },
        )
        return stats
