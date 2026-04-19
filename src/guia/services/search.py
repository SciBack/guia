"""SearchService — búsqueda semántica en el vector store."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sciback_core.ports.vector_store import VectorRecord, VectorStorePort
    from sciback_embeddings_e5 import E5EmbeddingAdapter


class SearchService:
    """Servicio de búsqueda semántica sobre el vector store.

    Args:
        store: Implementación de VectorStorePort (pgvector en producción).
        embedder: E5EmbeddingAdapter para generar el vector de la query.
    """

    def __init__(self, store: VectorStorePort, embedder: E5EmbeddingAdapter) -> None:
        self._store = store
        self._embedder = embedder

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        min_score: float = 0.0,
        filter: dict[str, object] | None = None,
    ) -> list[VectorRecord]:
        """Busca documentos relevantes para la query.

        Args:
            query: Texto de búsqueda del usuario.
            limit: Máximo de resultados a retornar.
            min_score: Score mínimo de similitud (0.0-1.0).
            filter: Filtro de metadatos (ej. {"source": "dspace"}).

        Returns:
            Lista de VectorRecord ordenada por score descendente.
        """
        query_vector = self._embedder.embed_query(query)
        return self._store.search(query_vector, limit=limit, min_score=min_score, filter=filter)

    def embed_query(self, query: str) -> list[float]:
        """Retorna el vector de embedding de la query.

        Args:
            query: Texto a embeber.

        Returns:
            Vector de floats (1024 dimensiones con E5).
        """
        return self._embedder.embed_query(query)
