"""Cliente del reranker (cross-encoder) que sirve el sidecar de embeddings.

Por qué un paso más después de la búsqueda híbrida: BM25 y kNN puntúan la
consulta y el documento por separado —uno por solapamiento léxico, el otro por
cercanía de dos vectores calculados de forma independiente—. El cross-encoder
lee el par junto y puntúa esa relación concreta, que es lo que de verdad
interesa. A cambio no se puede precomputar: cuesta una pasada del modelo por
documento, así que solo se aplica a los primeros candidatos.

Dónde vive el modelo: en el sidecar (``guia.embeddings_sidecar``), por la misma
razón que el embedder — una sola copia en RAM para api, chainlit y workers.

Política de fallo: si el reranker no responde, se devuelve el orden de la
fusión sin tocar. Un reranker caído degrada la calidad del ranking; nunca debe
dejar al usuario sin respuesta.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

__all__ = ["RerankClient"]


class RerankClient:
    """Reordena candidatos llamando a ``POST /api/rerank`` del sidecar."""

    def __init__(
        self,
        base_url: str,
        *,
        top_n: int = 30,
        timeout_s: float = 20.0,
    ) -> None:
        self._url = base_url.rstrip("/") + "/api/rerank"
        self._top_n = top_n
        self._timeout = timeout_s

    async def rerank(
        self,
        query: str,
        hits: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Devuelve los ``limit`` hits mejor puntuados por el cross-encoder.

        Args:
            query: Consulta del usuario, sin prefijos de embedding.
            hits: Candidatos de la búsqueda híbrida, ya ordenados por fusión.
            limit: Cuántos devolver.

        Returns:
            Los hits reordenados. Ante cualquier fallo, ``hits[:limit]`` tal
            cual llegaron — degradar el orden es aceptable; caerse, no.
        """
        if not hits or not query:
            return hits[:limit]

        # Solo la cabeza entra al cross-encoder: es donde el reordenamiento
        # cambia algo, y el coste crece linealmente con lo que se le mande.
        candidates = hits[: self._top_n]
        documents = [_hit_to_text(h) for h in candidates]

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._url,
                    json={"query": query, "documents": documents},
                )
                response.raise_for_status()
                results = response.json().get("results", [])
        except Exception as exc:
            logger.warning("rerank_failed_keeping_fusion_order", extra={"exc": str(exc)})
            return hits[:limit]

        reordered: list[dict[str, Any]] = []
        for item in results:
            idx = item.get("index")
            if not isinstance(idx, int) or not 0 <= idx < len(candidates):
                continue
            hit = dict(candidates[idx])
            # El score de fusión se conserva: sirve para depurar por qué un
            # documento llegó hasta aquí antes de que el reranker opinara.
            hit["fusion_score"] = hit.get("score")
            hit["score"] = item.get("score")
            reordered.append(hit)

        if not reordered:
            logger.warning("rerank_returned_nothing_usable")
            return hits[:limit]

        # La cola que no entró al cross-encoder queda detrás, en su orden.
        return (reordered + hits[self._top_n :])[:limit]


def _hit_to_text(hit: dict[str, Any]) -> str:
    """Texto que ve el cross-encoder por cada candidato.

    Título y resumen: es todo lo que hay hoy en el índice —la ingesta es de
    metadatos OAI-PMH, sin texto completo—. Cuando entre el texto completo, este
    es el punto donde debe pasarse el pasaje concreto y no la ficha entera.
    """
    parts = [str(hit.get("title") or ""), str(hit.get("abstract") or "")]
    return " ".join(p for p in parts if p).strip()
