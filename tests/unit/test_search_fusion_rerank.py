"""SearchAdapter: elección de fusión y paso de reranking."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from guia.search.backend import SearchAdapter, get_search_adapter
from guia.search.rerank import RerankClient


class _Hit:
    """SearchHit mínimo — el adapter solo lee id, score y source."""

    def __init__(self, doc_id: str, score: float = 1.0) -> None:
        self.id = doc_id
        self.score = score
        self.entity_type = "publication"
        self.source: dict[str, Any] = {"id": doc_id, "title": f"Título {doc_id}"}


class _Response:
    def __init__(self, hits: list[_Hit]) -> None:
        self.hits = hits


def _os_port(hits: list[_Hit]) -> AsyncMock:
    port = AsyncMock()
    port.rrf_hybrid = AsyncMock(return_value=_Response(hits))
    port.hybrid = AsyncMock(return_value=_Response(hits))
    return port


@pytest.mark.asyncio
async def test_default_fusion_is_rrf() -> None:
    port = _os_port([_Hit("a")])
    adapter = SearchAdapter(port)

    await adapter.hybrid_dicts("consulta", [0.1], limit=5)

    port.rrf_hybrid.assert_awaited_once()
    port.hybrid.assert_not_awaited()


@pytest.mark.asyncio
async def test_weighted_fusion_still_reachable_for_ab_testing() -> None:
    port = _os_port([_Hit("a")])
    adapter = SearchAdapter(port, fusion="weighted")

    await adapter.hybrid_dicts("consulta", [0.1], limit=5)

    port.hybrid.assert_awaited_once()
    port.rrf_hybrid.assert_not_awaited()


@pytest.mark.asyncio
async def test_rrf_receives_candidate_pool_not_the_final_limit() -> None:
    """La fusión necesita material: se piden candidates, se devuelven limit."""
    port = _os_port([_Hit(str(i)) for i in range(40)])
    adapter = SearchAdapter(port, candidates=50, rrf_k=60)

    hits = await adapter.hybrid_dicts("consulta", [0.1], limit=5)

    assert port.rrf_hybrid.call_args.kwargs["candidates"] == 50
    assert port.rrf_hybrid.call_args.kwargs["rrf_k"] == 60
    assert len(hits) == 5


@pytest.mark.asyncio
async def test_reranker_reorders_and_keeps_fusion_score(monkeypatch) -> None:
    """El orden final lo pone el cross-encoder; el score de fusión se conserva."""
    port = _os_port([_Hit("a", 0.9), _Hit("b", 0.8), _Hit("c", 0.7)])
    reranker = RerankClient("http://sidecar:11434")

    async def fake_post(self, url, **kwargs):  # noqa: ANN001, ANN202
        # El cross-encoder invierte el orden de la fusión.
        return _HttpResponse(
            {"results": [{"index": 2, "score": 9.0}, {"index": 0, "score": 1.0}]}
        )

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    adapter = SearchAdapter(port, reranker=reranker)

    hits = await adapter.hybrid_dicts("consulta", [0.1], limit=5)

    assert [h["id"] for h in hits] == ["c", "a"]
    assert hits[0]["score"] == 9.0
    assert hits[0]["fusion_score"] == 0.7


@pytest.mark.asyncio
async def test_reranker_down_degrades_to_fusion_order(monkeypatch) -> None:
    """Un reranker caído empeora el ranking; jamás deja al usuario sin respuesta."""
    port = _os_port([_Hit("a", 0.9), _Hit("b", 0.8)])

    async def boom(self, url, **kwargs):  # noqa: ANN001, ANN202
        raise RuntimeError("connection refused")

    monkeypatch.setattr("httpx.AsyncClient.post", boom)
    adapter = SearchAdapter(port, reranker=RerankClient("http://sidecar:11434"))

    hits = await adapter.hybrid_dicts("consulta", [0.1], limit=5)

    assert [h["id"] for h in hits] == ["a", "b"]


@pytest.mark.asyncio
async def test_opensearch_down_falls_back_to_pgvector() -> None:
    """El fallback previo sigue vivo tras meter fusión y reranking en medio."""
    port = AsyncMock()
    port.rrf_hybrid = AsyncMock(side_effect=RuntimeError("cluster unreachable"))

    class _Record:
        id = "pg-1"
        score = 0.5
        metadata = {"title": "Desde pgvector"}

    class _Store:
        def search(self, vector, limit, min_score):  # noqa: ANN001, ANN202
            return [_Record()]

    adapter = SearchAdapter(port, _Store())  # type: ignore[arg-type]

    hits = await adapter.hybrid_dicts("consulta", [0.1], limit=5)

    assert [h["id"] for h in hits] == ["pg-1"]


def test_factory_builds_reranker_only_when_enabled() -> None:
    """rerank_enabled=False no debe instanciar nada: el modelo cuesta RAM."""

    class _Settings:
        search_fusion = "rrf"
        search_rrf_k = 60
        search_candidates = 50
        rerank_enabled = False
        rerank_url = "http://embeddings:11434"
        rerank_top_n = 30
        rerank_timeout_s = 20.0

    adapter = get_search_adapter("opensearch", None, _Settings())

    assert adapter is not None
    assert adapter._reranker is None


class _HttpResponse:
    """Respuesta httpx mínima para los tests del reranker."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload
