"""Tests del sidecar de embeddings (protocolo Ollama + routing por prefijo)."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sciback_core.ports.llm import EmbeddingResponse

from guia import embeddings_sidecar
from guia.embeddings_sidecar import _state, app


def _fake_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.embed_query.return_value = [0.1] * 1024
    adapter.embed_passages.return_value = EmbeddingResponse(
        embeddings=[[0.2] * 1024], model="stub", input_tokens=0
    )
    return adapter


def _client_ready() -> TestClient:
    _state.adapter = _fake_adapter()
    _state.ready = True
    # No usar el lifespan real (cargaría el modelo ONNX de 2.5GB).
    return TestClient(app, raise_server_exceptions=True)


def teardown_function() -> None:
    _state.adapter = None
    _state.ready = False


def test_health_503_mientras_carga() -> None:
    _state.ready = False
    client = TestClient(app)
    assert client.get("/health").status_code == 503


def test_health_200_con_modelo_listo() -> None:
    client = _client_ready()
    assert client.get("/health").json() == {"ready": True}


def test_query_prefijada_va_a_embed_query() -> None:
    """Texto con 'query: ' usa query_embed (paridad con el path directo)."""
    client = _client_ready()
    resp = client.post(
        "/api/embeddings", json={"model": "e5", "prompt": "query: tesis de IA"}
    )
    assert resp.status_code == 200
    assert len(resp.json()["embedding"]) == 1024
    _state.adapter.embed_query.assert_called_once_with("query: tesis de IA")  # type: ignore[union-attr]
    _state.adapter.embed_passages.assert_not_called()  # type: ignore[union-attr]


def test_todo_lo_no_query_va_a_embed_passages() -> None:
    """Cualquier texto que no empiece con 'query: ' usa el path de passages
    (model.embed) — tanto con prefijo 'passage: ' como sin prefijo alguno."""
    client = _client_ready()
    for prompt in ("passage: contenido del documento", "texto sin prefijo"):
        resp = client.post("/api/embeddings", json={"model": "e5", "prompt": prompt})
        assert resp.status_code == 200
        assert resp.json()["embedding"] == [0.2] * 1024
    assert _state.adapter.embed_passages.call_count == 2  # type: ignore[union-attr]
    _state.adapter.embed_query.assert_not_called()  # type: ignore[union-attr]


def test_excepcion_del_modelo_retorna_500_con_detalle() -> None:
    """Un fallo de inferencia produce 500 con detail útil (el cliente
    OllamaLLMAdapter lo muestra en su IntegrationError), no un 500 mudo."""
    client = _client_ready()
    _state.adapter.embed_query.side_effect = RuntimeError("onnx kaput")  # type: ignore[union-attr]
    resp = client.post("/api/embeddings", json={"model": "e5", "prompt": "query: x"})
    assert resp.status_code == 500
    assert "onnx kaput" in resp.json()["detail"]


async def test_inferencias_concurrentes_se_serializan() -> None:
    """El semáforo garantiza una inferencia ONNX a la vez (sesión compartida)."""
    import time

    from httpx import ASGITransport, AsyncClient

    active = {"now": 0, "max": 0}

    def _slow_embed(prompt: str) -> list[float]:
        active["now"] += 1
        active["max"] = max(active["max"], active["now"])
        time.sleep(0.05)
        active["now"] -= 1
        return [0.1] * 1024

    adapter = MagicMock()
    adapter.embed_query.side_effect = _slow_embed
    _state.adapter = adapter
    _state.ready = True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        import asyncio as _asyncio

        results = await _asyncio.gather(*[
            client.post("/api/embeddings", json={"model": "e5", "prompt": "query: x"})
            for _ in range(4)
        ])

    assert all(r.status_code == 200 for r in results)
    assert active["max"] == 1, f"hubo {active['max']} inferencias simultáneas"


def test_prompt_vacio_retorna_400() -> None:
    client = _client_ready()
    resp = client.post("/api/embeddings", json={"model": "e5", "prompt": ""})
    assert resp.status_code == 400


def test_embeddings_503_si_modelo_no_listo() -> None:
    _state.ready = False
    client = TestClient(app)
    resp = client.post("/api/embeddings", json={"model": "e5", "prompt": "query: x"})
    assert resp.status_code == 503


def test_build_adapter_usa_prefijos_vacios() -> None:
    """El cliente E5 ya antepone prefijos — el adapter local NO debe duplicarlos."""
    import sys
    from unittest.mock import patch

    fake_module = MagicMock()
    captured: dict[str, object] = {}

    def _fake_config(**kwargs: object) -> object:
        captured.update(kwargs)
        return MagicMock()

    fake_module.FastEmbedConfig = _fake_config
    fake_module.FastEmbedAdapter = MagicMock()
    with patch.dict(sys.modules, {"sciback_embeddings_fastembed": fake_module}):
        embeddings_sidecar._build_adapter()

    assert captured["query_prefix"] == ""
    assert captured["passage_prefix"] == ""
