"""Search backend factory — ADR-029.

Soporta tres modos configurables via SEARCH_BACKEND:
  pgvector   — usa solo VectorStorePort (pgvector), sin OpenSearch
  opensearch — usa solo OpenSearchSearchPort (async nativo)
  dual       — escribe a ambos, lee de OpenSearch con fallback a pgvector

M4: ChatService es async — usar hybrid_dicts() con await directamente.
    hybrid_sync() se mantiene solo para Celery workers y contextos síncronos.

La lectura tiene dos etapas configurables sobre OpenSearch:

  1. **Fusión** de las ramas BM25 y kNN. Default ``rrf`` (Reciprocal Rank
     Fusion), que fusiona posiciones en vez de scores. La alternativa
     ``weighted`` suma los scores de ambas ramas y se conserva solo para
     comparar: BM25 no está acotado y el score kNN vive en (0, 1], así que esa
     suma la gana BM25 casi siempre y los pesos no significan lo que aparentan.
  2. **Reranking** opcional con cross-encoder sobre la cabeza de la fusión.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sciback_core.ports.vector_store import VectorStorePort
    from guia.search.rerank import RerankClient
    from sciback_core.search import SearchFilters, SearchHit, SearchResponse

logger = logging.getLogger(__name__)

__all__ = ["SearchAdapter", "get_search_adapter"]


def _hit_to_dict(h: SearchHit) -> dict[str, Any]:
    """Convierte un SearchHit de OpenSearch a dict compatible con _hits_to_context."""
    return {
        "id": str(h.id),
        "score": h.score,
        "title": h.source.get("title", ""),
        "abstract": h.source.get("abstract", ""),
        "authors": h.source.get("authors", []),
        "year": h.source.get("publication_year"),
        "url": h.source.get("external_resource_uri"),
        "source": h.source.get("source", ""),
        "source_type": h.source.get("source_type", ""),
        "subjects": h.source.get("subjects", []),
        "metadata": h.source,
    }


def _pgvector_record_to_dict(r: object) -> dict[str, Any]:
    """Convierte un VectorRecord de pgvector a dict compatible con _hits_to_context."""
    meta = getattr(r, "metadata", {})
    return {
        "id": getattr(r, "id", ""),
        "score": getattr(r, "score", 0.0),
        "title": meta.get("title", ""),
        "abstract": meta.get("abstract", ""),
        "authors": meta.get("authors", []),
        "year": meta.get("year"),
        "url": meta.get("url"),
        "metadata": meta,
    }


class SearchAdapter:
    """Adapter sobre OpenSearchSearchPort con métodos async (M4) y sync (Celery).

    M4: ChatService usa hybrid_dicts() con await.
    Celery workers usan hybrid_sync() / index_sync() sin event loop.
    """

    def __init__(
        self,
        opensearch_port: object,
        pgvector_port: VectorStorePort | None = None,
        *,
        fusion: str = "rrf",
        rrf_k: int = 60,
        candidates: int = 50,
        reranker: RerankClient | None = None,
    ) -> None:
        self._os = opensearch_port
        self._pg = pgvector_port
        self._fusion = fusion
        self._rrf_k = rrf_k
        self._candidates = candidates
        self._reranker = reranker

    # ── M4: métodos async nativos ──────────────────────────────────────────────

    async def hybrid_dicts(
        self,
        text: str,
        vector: list[float],
        weights: tuple[float, float] = (0.3, 0.7),
        filters: SearchFilters | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """M4: hybrid search async que retorna list[dict] para ChatService.

        Fusiona (RRF o ponderada), rerankea si hay cross-encoder y recorta a
        ``limit``. Fallback a pgvector si OpenSearch falla.
        """
        try:
            result: SearchResponse = await self._fused(text, vector, weights, filters)
        except Exception as exc:
            logger.warning("opensearch_hybrid_failed", extra={"exc": str(exc)})
            return await self._pgvector_fallback(vector, limit)

        hits = [_hit_to_dict(h) for h in result.hits]
        if self._reranker is not None:
            return await self._reranker.rerank(text, hits, limit)
        return hits[:limit]

    async def _fused(
        self,
        text: str,
        vector: list[float],
        weights: tuple[float, float],
        filters: SearchFilters | None,
    ) -> SearchResponse:
        """Ejecuta la búsqueda híbrida con la estrategia de fusión configurada."""
        if self._fusion == "rrf_native":
            # Fusion dentro del cluster. Si el pipeline no existe o el
            # OpenSearch no trae el procesador, no se deja al usuario sin
            # respuesta: se cae a la fusion en cliente, que da el mismo
            # ranking sin depender del servidor.
            try:
                return await self._os.rrf_hybrid_native(  # type: ignore[union-attr]
                    text=text,
                    vector=vector,
                    filters=filters,
                    candidates=self._candidates,
                )
            except Exception as exc:
                logger.warning(
                    "rrf_nativo_no_disponible_se_usa_el_de_cliente",
                    extra={"exc": str(exc)},
                )

        if self._fusion in ("rrf", "rrf_native"):
            return await self._os.rrf_hybrid(  # type: ignore[union-attr]
                text=text,
                vector=vector,
                filters=filters,
                candidates=self._candidates,
                rrf_k=self._rrf_k,
                weights=weights,
            )
        return await self._os.hybrid(  # type: ignore[union-attr]
            text=text,
            vector=vector,
            weights=weights,
            filters=filters,
        )

    async def _pgvector_fallback(
        self, vector: list[float], limit: int
    ) -> list[dict[str, Any]]:
        """Fallback a pgvector en un thread (es sync)."""
        if self._pg is None:
            return []
        logger.info("falling_back_to_pgvector")
        records = await asyncio.to_thread(
            self._pg.search, vector, limit=limit, min_score=0.3
        )
        return [_pgvector_record_to_dict(r) for r in records]

    async def index_async(self, entity: object) -> None:
        """Indexa una entidad en OpenSearch (async nativo — workers Celery async)."""
        await self._os.index(entity)  # type: ignore[union-attr]

    async def hybrid_async(
        self,
        text: str,
        vector: list[float],
        weights: tuple[float, float] = (0.3, 0.7),
        filters: SearchFilters | None = None,
    ) -> SearchResponse:
        """Retorna SearchResponse crudo — para casos donde se necesita el objeto completo."""
        return await self._os.hybrid(  # type: ignore[union-attr]
            text=text,
            vector=vector,
            weights=weights,
            filters=filters,
        )

    async def close(self) -> None:
        if hasattr(self._os, "close"):
            await self._os.close()  # type: ignore[union-attr]

    # ── Sync: solo para Celery workers (sin event loop) ───────────────────────

    def hybrid_sync(
        self,
        text: str,
        vector: list[float],
        weights: tuple[float, float] = (0.3, 0.7),
        filters: SearchFilters | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Sync bridge con asyncio.run() — solo para Celery workers.

        En contextos async usar hybrid_dicts() con await.
        """
        try:
            result: SearchResponse = asyncio.run(
                self._fused(text, vector, weights, filters)
            )
            hits = [_hit_to_dict(h) for h in result.hits]
            if self._reranker is not None:
                return asyncio.run(self._reranker.rerank(text, hits, limit))
            return hits[:limit]
        except Exception as exc:
            logger.warning("opensearch_hybrid_failed", extra={"exc": str(exc)})
            if self._pg is not None:
                logger.info("falling_back_to_pgvector")
                records = self._pg.search(vector, limit=limit, min_score=0.3)
                return [_pgvector_record_to_dict(r) for r in records]
            return []

    def index_sync(self, entity: object) -> None:
        """Indexa en OpenSearch vía asyncio.run() — solo para Celery workers."""
        try:
            asyncio.run(self._os.index(entity))  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("opensearch_index_failed", extra={"exc": str(exc)})


# Alias de compatibilidad M3 → M4
SyncSearchAdapter = SearchAdapter


def get_search_adapter(
    backend: str,
    pgvector_store: VectorStorePort | None = None,
    settings: object | None = None,
) -> SearchAdapter | None:
    """Factory de search backend según configuración.

    Args:
        backend: "pgvector" | "opensearch" | "dual"
        pgvector_store: instancia existente de PgVectorStore (para reutilizar)
        settings: GUIASettings. Si es None se usan los defaults del adapter —
            los tests y los scripts que solo indexan no necesitan pasarlo.

    Returns:
        SearchAdapter si backend incluye OpenSearch, None si es solo pgvector.
    """
    if backend == "pgvector":
        return None

    try:
        from sciback_search_opensearch import OpenSearchSearchPort, OpenSearchSettings
        os_port = OpenSearchSearchPort(OpenSearchSettings(_env_file=None))
        pg_fallback = pgvector_store if backend == "dual" else None

        fusion = getattr(settings, "search_fusion", "rrf")
        rrf_k = getattr(settings, "search_rrf_k", 60)
        candidates = getattr(settings, "search_candidates", 50)

        reranker: RerankClient | None = None
        if getattr(settings, "rerank_enabled", False):
            from guia.search.rerank import RerankClient as _RerankClient

            reranker = _RerankClient(
                settings.rerank_url,  # type: ignore[union-attr]
                top_n=settings.rerank_top_n,  # type: ignore[union-attr]
                timeout_s=settings.rerank_timeout_s,  # type: ignore[union-attr]
            )

        # logger es stdlib logging.Logger (no structlog) — kwargs van en extra={}
        logger.info(
            "search_backend_initialized",
            extra={
                "backend": backend,
                "fusion": fusion,
                "rerank": reranker is not None,
            },
        )
        return SearchAdapter(
            os_port,
            pg_fallback,
            fusion=fusion,
            rrf_k=rrf_k,
            candidates=candidates,
            reranker=reranker,
        )
    except Exception as exc:
        logger.warning(
            "opensearch_init_failed",
            extra={"exc": str(exc), "fallback": "pgvector"},
        )
        return None
