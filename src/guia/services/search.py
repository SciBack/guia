"""SearchService — búsqueda semántica con Parent-Document Retrieval (P3.1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sciback_core.ports.vector_store import VectorRecord, VectorStorePort
    from sciback_embeddings_e5 import E5EmbeddingAdapter


def dedupe_by_parent(
    hits: list[VectorRecord],
    store: VectorStorePort,
) -> list[VectorRecord]:
    """Colapsa chunks al documento padre y conserva el mejor score.

    Args:
        hits: Resultados crudos del vector store (mezcla padres + chunks).
        store: Vector store para recuperar el padre por ID si no está en hits.

    Returns:
        Lista deduplicada por parent_id (o id del padre directo).
        Cada parent aparece una sola vez con el max(score) de sus chunks.
        Orden preservado: el primer chunk encontrado define la posición.

    Algoritmo:
        1. Por cada hit, determinar su 'group_id':
           - Si es chunk (metadata.is_chunk=True): group_id = parent_id
           - Si es padre directo: group_id = hit.id
        2. Agrupar y mantener max(score) por grupo.
        3. Para grupos donde solo se vieron chunks (no el padre), recuperar
           el padre del store por su id.
    """
    if not hits:
        return []

    # Map group_id → (best_record, best_score, is_parent_fetched)
    groups: dict[str, tuple[VectorRecord, float, bool]] = {}
    order: list[str] = []  # preserva orden de primera aparición

    for hit in hits:
        meta = hit.metadata or {}
        is_chunk = bool(meta.get("is_chunk", False))
        parent_id = str(meta.get("parent_id", "")) if is_chunk else hit.id
        group_id = parent_id

        if group_id not in groups:
            order.append(group_id)
            groups[group_id] = (hit, hit.score, not is_chunk)
        else:
            prev_record, prev_score, has_parent = groups[group_id]
            new_score = max(prev_score, hit.score)
            # Si vino el padre directo y antes solo había chunks, prioritizar padre
            if not is_chunk and not has_parent:
                groups[group_id] = (hit, new_score, True)
            else:
                # Conservar el mejor record (padre si lo hay)
                best_record = (
                    prev_record
                    if has_parent or hit.score <= prev_score
                    else hit
                )
                groups[group_id] = (best_record, new_score, has_parent)

    # Para grupos que solo tienen chunks (sin padre fetcheado), recuperar padre
    out: list[VectorRecord] = []
    from dataclasses import replace as _replace  # no-op, BaseModel no es dataclass

    for gid in order:
        record, best_score, has_parent = groups[gid]
        if not has_parent:
            parent = store.get(gid)
            if parent is not None:
                # Reemplazar score del parent con el max de los chunks
                record = parent.model_copy(update={"score": best_score})
            # else: dejamos el chunk como mejor representación (parent no existe)
        else:
            # Asegurar que el score reflejado es el max
            if record.score != best_score:
                record = record.model_copy(update={"score": best_score})
        out.append(record)

    return out


class SearchService:
    """Servicio de búsqueda semántica sobre el vector store.

    Args:
        store: Implementación de VectorStorePort (pgvector en producción).
        embedder: E5EmbeddingAdapter para generar el vector de la query.
        dedupe_chunks: Si True, aplica Parent-Document Retrieval (default).
    """

    def __init__(
        self,
        store: VectorStorePort,
        embedder: E5EmbeddingAdapter,
        *,
        dedupe_chunks: bool = True,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._dedupe_chunks = dedupe_chunks

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        min_score: float = 0.0,
        filter: dict[str, object] | None = None,
    ) -> list[VectorRecord]:
        """Busca documentos relevantes con Parent-Document Retrieval (P3.1).

        Si el store contiene chunks indexados con parent_id, se piden más
        resultados crudos que `limit` y se deduplica al padre. Esto evita
        que múltiples chunks del mismo documento dominen el top-K.

        Args:
            query: Texto de búsqueda.
            limit: Resultados finales a retornar.
            min_score: Umbral de score.
            filter: Filtro de metadatos.

        Returns:
            Lista deduplicada por parent_id, ordenada por score descendente.
        """
        query_vector = self._embedder.embed_query(query)
        # Pedir más para tener margen tras deduplicación. 3x es heurística.
        raw_limit = limit * 3 if self._dedupe_chunks else limit
        hits = self._store.search(
            query_vector, limit=raw_limit, min_score=min_score, filter=filter
        )

        if self._dedupe_chunks:
            hits = dedupe_by_parent(hits, self._store)

        return hits[:limit]

    def embed_query(self, query: str) -> list[float]:
        """Retorna el vector de embedding de la query."""
        return self._embedder.embed_query(query)
