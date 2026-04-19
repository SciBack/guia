"""Tests de integración de la API REST de GUIA.

Usa FastAPI TestClient con overrides de dependencias para no requerir
servicios externos (postgres, redis, LLMs).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sciback_core.ports.llm import InMemoryLLMAdapter
from sciback_core.ports.vector_store import InMemoryVectorStoreAdapter

from guia.api.app import create_app
from guia.api.deps import get_chat_service, get_container, get_harvester_service
from guia.config import GUIASettings, LLMMode
from guia.domain.chat import Intent
from guia.services.chat import ChatService

# ── Fixtures ──────────────────────────────────────────────────────────────────

class FakeEmbedder:
    embedding_dim = 8

    def embed_query(self, query: str) -> list[float]:
        return [0.1] * 8

    def embed_passages(self, texts: list[str]) -> object:
        from sciback_core.ports.llm import EmbeddingResponse
        return EmbeddingResponse(
            embeddings=[[0.1] * 8] * len(texts),
            model="stub-e5",
            input_tokens=0,
        )


def _make_chat_service(intent: str = "research", answer: str = "Respuesta de test") -> ChatService:
    return ChatService(
        synthesis_llm=InMemoryLLMAdapter(canned_response=answer, embedding_dim=8),
        store=InMemoryVectorStoreAdapter(dim=8),
        embedder=FakeEmbedder(),
        classifier_llm=InMemoryLLMAdapter(canned_response=intent, embedding_dim=8),
    )


@pytest.fixture
def test_settings() -> GUIASettings:
    """Settings para tests — sin leer del entorno."""
    return GUIASettings(
        guia_llm_mode=LLMMode.LOCAL,
        environment="development",
        redis_url="redis://localhost:6379/0",
    )


@pytest.fixture
def app_client(test_settings: GUIASettings) -> TestClient:
    """TestClient con container mock inyectado."""
    app = create_app(test_settings)

    # Mock del container — sin conexiones reales
    mock_container = MagicMock()
    mock_container.chat_service = _make_chat_service()
    mock_container.harvester_service = MagicMock()

    # Inyectar en app.state (para lifespan real necesitaríamos httpx, usamos override)
    app.state.container = mock_container
    app.state.settings = test_settings

    # Override de dependencias FastAPI
    app.dependency_overrides[get_container] = lambda: mock_container
    app.dependency_overrides[get_chat_service] = lambda: mock_container.chat_service
    app.dependency_overrides[get_harvester_service] = lambda: mock_container.harvester_service

    return TestClient(app, raise_server_exceptions=True)


# ── Tests /health ─────────────────────────────────────────────────────────────

def test_health_ok(app_client: TestClient) -> None:
    """GET /health retorna 200 con status ok."""
    # Mock del redis ping en el container
    app_client.app.state.container._redis = MagicMock()
    app_client.app.state.container._redis.ping.return_value = True

    resp = app_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "environment" in data


# ── Tests POST /api/chat ───────────────────────────────────────────────────────

def test_chat_basic_request(app_client: TestClient) -> None:
    """POST /api/chat retorna 200 con respuesta válida."""
    resp = app_client.post("/api/chat", json={"query": "¿Qué tesis hay sobre IA?"})
    assert resp.status_code == 200

    data = resp.json()
    assert "answer" in data
    assert "intent" in data
    assert "sources" in data
    assert "model_used" in data
    assert "cached" in data
    assert "tokens_used" in data


def test_chat_response_structure(app_client: TestClient) -> None:
    """La respuesta tiene la estructura correcta."""
    resp = app_client.post("/api/chat", json={"query": "repositorio institucional"})
    data = resp.json()

    assert data["answer"] == "Respuesta de test"
    assert data["intent"] in [i.value for i in Intent]
    assert isinstance(data["sources"], list)
    assert isinstance(data["cached"], bool)
    assert isinstance(data["tokens_used"], int)


def test_chat_empty_query_returns_422(app_client: TestClient) -> None:
    """Query vacía retorna 422 Unprocessable Entity."""
    resp = app_client.post("/api/chat", json={"query": ""})
    assert resp.status_code == 422


def test_chat_missing_query_returns_422(app_client: TestClient) -> None:
    """Request sin campo query retorna 422."""
    resp = app_client.post("/api/chat", json={})
    assert resp.status_code == 422


def test_chat_with_session_id(app_client: TestClient) -> None:
    """POST /api/chat acepta session_id opcional."""
    resp = app_client.post(
        "/api/chat",
        json={"query": "tesis", "session_id": "ses-123"},
    )
    assert resp.status_code == 200


def test_chat_query_too_long_returns_422(app_client: TestClient) -> None:
    """Query de más de 2000 caracteres retorna 422."""
    long_query = "a" * 2001
    resp = app_client.post("/api/chat", json={"query": long_query})
    assert resp.status_code == 422


# ── Tests POST /api/admin/harvest ─────────────────────────────────────────────

def test_harvest_all_without_token_development(app_client: TestClient) -> None:
    """En development sin GUIA_ADMIN_TOKEN configurado, se permite el acceso."""
    import os
    os.environ.pop("GUIA_ADMIN_TOKEN", None)

    mock_harvester = app_client.app.state.container.harvester_service
    mock_harvester.harvest_dspace.return_value = {"total": 10, "ok": 8, "error": 2}
    mock_harvester.harvest_ojs.return_value = {"total": 5, "ok": 5, "error": 0}
    mock_harvester.harvest_alicia.return_value = {"total": 3, "ok": 3, "error": 0}

    resp = app_client.post("/api/admin/harvest", json={"source": "all"})
    assert resp.status_code == 200

    data = resp.json()
    assert "results" in data
    assert "message" in data


def test_harvest_dspace_only(app_client: TestClient) -> None:
    """Cosecha solo DSpace cuando source=dspace."""
    import os
    os.environ.pop("GUIA_ADMIN_TOKEN", None)

    mock_harvester = app_client.app.state.container.harvester_service
    mock_harvester.harvest_dspace.return_value = {"total": 10, "ok": 10, "error": 0}

    resp = app_client.post("/api/admin/harvest", json={"source": "dspace"})
    assert resp.status_code == 200

    data = resp.json()
    assert "dspace" in data["results"]
    assert "ojs" not in data["results"]


def test_harvest_invalid_source_returns_422(app_client: TestClient) -> None:
    """Source inválido retorna 422."""
    resp = app_client.post("/api/admin/harvest", json={"source": "invalid_source"})
    assert resp.status_code == 422
