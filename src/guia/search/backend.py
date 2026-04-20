"""Search backend factory — ADR-029.

Soporta tres modos configurables via SEARCH_BACKEND:
  pgvector   — usa solo VectorStorePort (pgvector), sin OpenSearch
  opensearch — usa solo OpenSearchSearchPort (async, wrapped a sync)
  dual       — escribe a ambos, lee de OpenSearch con fallback a pgvector

Nota M3→M4: el bridge sync/async usa asyncio.run() por llamada.
Esto es aceptable en M3 (requests no concurrentes a este nivel).
En M4 migrar ChatService a async y eliminar el wrapper.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sciback_core.ports.vector_store import VectorStorePort
    from sciback_core.search import SearchFilters, SearchResponse

logger = logging.getLogger(__name__)

__all__ = ["SyncSearchAdapter", "get_search_adapter"]


class SyncSearchAdapter:
    """Wrapper síncrono sobre OpenSearchSearchPort (async) para uso en ChatService.

    M3: usa asyncio.run() por llamada. M4: eliminar cuando ChatService sea async.
    """

    def __init__(
        self, opensearch_port: object, pgvector_port: VectorStorePort | None = None
    ) -> None:
        self._os = opensearch_port
        self._pg = pgvector_port

    def hybrid_sync(
        self,
        text: str,
        vector: list[float],
        weights: tuple[float, float] = (0.3, 0.7),
        filters: SearchFilters | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Llama hybrid() async de OpenSearch y retorna lista de dicts."""
        try:
            result: SearchResponse = asyncio.run(
                self._os.hybrid(  # type: ignore[union-attr]
                    text=text,
                    vector=vector,
                    weights=weights,
                    filters=filters,
                )
            )
            hits = result.hits[:limit]
            return [
                {
                    "id": str(h.id),
                    "score": h.score,
                    "title": h.source.get("title", ""),
                    "abstract": h.source.get("abstract", ""),
                    "authors": h.source.get("authors", []),
                    "year": h.source.get("publication_year"),
                    "url": h.source.get("external_resource_uri"),
                    "metadata": h.source,
                }
                for h in hits
            ]
        except Exception as exc:
            logger.warning("opensearch_hybrid_failed", exc=str(exc))
            if self._pg is not None:
                logger.info("falling_back_to_pgvector")
                records = self._pg.search(vector, limit=limit, min_score=0.3)
                return [
                    {
                        "id": r.id,
                        "score": r.score,
                        "title": r.metadata.get("title", ""),
                        "abstract": r.metadata.get("abstract", ""),
                        "authors": r.metadata.get("authors", []),
                        "year": r.metadata.get("year"),
                        "url": r.metadata.get("url"),
                        "metadata": r.metadata,
                    }
                    for r in records
                ]
            return []

    def index_sync(self, entity: object) -> None:
        """Indexa una entidad en OpenSearch (sync wrapper)."""
        try:
            asyncio.run(self._os.index(entity))  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("opensearch_index_failed", exc=str(exc))

    async def index_async(self, entity: object) -> None:
        """Indexa una entidad en OpenSearch (async nativo — para workers Celery)."""
        await self._os.index(entity)  # type: ignore[union-attr]

    async def hybrid_async(
        self,
        text: str,
        vector: list[float],
        weights: tuple[float, float] = (0.3, 0.7),
        filters: SearchFilters | None = None,
    ) -> SearchResponse:
        """Hybrid search async nativo — para uso en contextos async (M4)."""
        return await self._os.hybrid(  # type: ignore[union-attr]
            text=text,
            vector=vector,
            weights=weights,
            filters=filters,
        )

    async def close(self) -> None:
        if hasattr(self._os, "close"):
            await self._os.close()  # type: ignore[union-attr]


def get_search_adapter(
    backend: str,
    pgvector_store: VectorStorePort | None = None,
) -> SyncSearchAdapter | None:
    """Factory de search backend según configuración.

    Args:
        backend: "pgvector" | "opensearch" | "dual"
        pgvector_store: instancia existente de PgVectorStore (para reutilizar)

    Returns:
        SyncSearchAdapter si backend incluye OpenSearch, None si es solo pgvector.
    """
    if backend == "pgvector":
        # Sin OpenSearch — ChatService sigue usando pgvector directo
        return None

    try:
        from sciback_search_opensearch import OpenSearchSearchPort, OpenSearchSettings
        os_port = OpenSearchSearchPort(OpenSearchSettings(_env_file=None))
        pg_fallback = pgvector_store if backend == "dual" else None
        logger.info("search_backend_initialized", backend=backend)
        return SyncSearchAdapter(os_port, pg_fallback)
    except Exception as exc:
        logger.warning(
            "opensearch_init_failed",
            exc=str(exc),
            fallback="pgvector",
        )
        return None
