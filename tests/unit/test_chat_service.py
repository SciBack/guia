"""Tests del ChatService — núcleo del asistente GUIA.

Usa InMemoryLLMAdapter y InMemoryVectorStoreAdapter para tests sin servicios externos.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from sciback_core.ports.llm import InMemoryLLMAdapter
from sciback_core.ports.vector_store import InMemoryVectorStoreAdapter

from guia.domain.chat import ChatRequest, ChatResponse, Intent
from guia.services.chat import ChatService

# ── Fixtures ──────────────────────────────────────────────────────────────────

class FakeEmbedder:
    """Embedder stub que retorna vectores de dim=8."""

    embedding_dim = 8

    def embed_query(self, query: str) -> list[float]:
        return [0.1] * 8

    def embed_passages(self, texts: list[str]) -> object:
        from sciback_core.ports.llm import EmbeddingResponse
        return EmbeddingResponse(
            embeddings=[[0.1] * 8] * len(texts),
            model="stub-e5",
            input_tokens=sum(len(t.split()) for t in texts),
        )


def _make_service(
    canned_response: str = "Respuesta de prueba",
    intent_response: str = "research",
    store: InMemoryVectorStoreAdapter | None = None,
    cache: object = None,
) -> ChatService:
    synthesis_llm = InMemoryLLMAdapter(canned_response=canned_response, embedding_dim=8)
    classifier_llm = InMemoryLLMAdapter(canned_response=intent_response, embedding_dim=8)
    _store = store or InMemoryVectorStoreAdapter(dim=8)
    embedder = FakeEmbedder()

    return ChatService(
        synthesis_llm=synthesis_llm,
        store=_store,
        embedder=embedder,
        classifier_llm=classifier_llm,
        cache=cache,  # type: ignore[arg-type]
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_answer_returns_chat_response() -> None:
    """answer() retorna un ChatResponse válido."""
    service = _make_service()
    request = ChatRequest(query="¿Qué tesis hay sobre IA?")
    response = service.answer(request)

    assert isinstance(response, ChatResponse)
    assert response.answer == "Respuesta de prueba"
    assert isinstance(response.intent, Intent)


def test_answer_research_intent_calls_llm() -> None:
    """Para intent RESEARCH, se llama al LLM de síntesis."""
    service = _make_service(intent_response="research")
    request = ChatRequest(query="tesis machine learning")
    response = service.answer(request)

    assert response.intent == Intent.RESEARCH
    assert response.answer == "Respuesta de prueba"


def test_answer_out_of_scope_no_llm_call() -> None:
    """Para OUT_OF_SCOPE, no se llama al LLM de síntesis."""
    synthesis = InMemoryLLMAdapter(canned_response="no debería llamarse")
    classifier = InMemoryLLMAdapter(canned_response="out_of_scope")
    store = InMemoryVectorStoreAdapter(dim=8)

    service = ChatService(
        synthesis_llm=synthesis,
        store=store,
        embedder=FakeEmbedder(),
        classifier_llm=classifier,
    )

    request = ChatRequest(query="¿Cuál es la capital de Argentina?")
    response = service.answer(request)

    assert response.intent == Intent.OUT_OF_SCOPE
    # El LLM de síntesis NO debe haberse llamado
    assert len(synthesis.complete_calls) == 0


def test_answer_campus_returns_unavailable_message() -> None:
    """Para CAMPUS, retorna mensaje de no disponible (Fase 0)."""
    service = _make_service(intent_response="campus")
    request = ChatRequest(query="¿Cuánto debo en biblioteca?")
    response = service.answer(request)

    assert response.intent == Intent.CAMPUS
    assert "campus" in response.answer.lower() or "disponible" in response.answer.lower()


def test_answer_uses_vector_store_results() -> None:
    """Para RESEARCH, busca en el vector store y construye contexto."""
    store = InMemoryVectorStoreAdapter(dim=8)
    store.upsert(
        "doc-1",
        [0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        metadata={
            "title": "IA en Educación",
            "abstract": "Impacto de la IA en universidades.",
            "source": "dspace",
        },
    )

    synthesis = InMemoryLLMAdapter(canned_response="Síntesis con contexto", embedding_dim=8)
    classifier = InMemoryLLMAdapter(canned_response="research", embedding_dim=8)

    service = ChatService(
        synthesis_llm=synthesis,
        store=store,
        embedder=FakeEmbedder(),
        classifier_llm=classifier,
    )

    service.answer(ChatRequest(query="inteligencia artificial"))

    # El LLM de síntesis fue llamado con mensajes que incluyen el contexto
    assert len(synthesis.complete_calls) == 1
    system_msg = synthesis.complete_calls[0][0]
    assert system_msg.role == "system"


def test_answer_with_cache_hit_returns_cached_response() -> None:
    """Si el caché tiene hit, se retorna la respuesta cacheada."""
    cached_response = ChatResponse(
        answer="Respuesta desde caché",
        intent=Intent.GENERAL,
        sources=[],
        model_used="stub",
        cached=False,
        tokens_used=5,
    )

    mock_cache = MagicMock()
    mock_cache.get.return_value = cached_response

    service = _make_service(cache=mock_cache)
    response = service.answer(ChatRequest(query="consulta repetida"))

    assert response.cached is True
    assert response.answer == "Respuesta desde caché"
    # El LLM NO debe haberse llamado
    service._synthesis_llm.complete_calls == []  # type: ignore[union-attr]


def test_answer_with_cache_miss_sets_cache() -> None:
    """Con cache miss, la respuesta se almacena en caché."""
    mock_cache = MagicMock()
    mock_cache.get.return_value = None  # miss

    service = _make_service(cache=mock_cache, intent_response="general")
    service.answer(ChatRequest(query="consulta nueva"))

    mock_cache.set.assert_called_once()


def test_answer_without_cache_works() -> None:
    """ChatService funciona sin caché configurado."""
    service = _make_service(cache=None)
    response = service.answer(ChatRequest(query="prueba sin caché"))
    assert isinstance(response, ChatResponse)


def test_answer_sources_from_store() -> None:
    """Las fuentes del vector store se incluyen en la respuesta."""
    store = InMemoryVectorStoreAdapter(dim=8)
    store.upsert(
        "tesis-001",
        [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        metadata={
            "title": "Tesis sobre blockchain",
            "abstract": "Aplicación de blockchain en sistemas universitarios.",
            "source": "dspace",
            "year": 2024,
        },
    )

    synthesis = InMemoryLLMAdapter(canned_response="Blockchain en universidades.", embedding_dim=8)
    classifier = InMemoryLLMAdapter(canned_response="research", embedding_dim=8)

    service = ChatService(
        synthesis_llm=synthesis,
        store=store,
        embedder=FakeEmbedder(),
        classifier_llm=classifier,
    )

    response = service.answer(ChatRequest(query="blockchain universidad"))
    assert len(response.sources) >= 1
    assert response.sources[0].title == "Tesis sobre blockchain"


def test_answer_intent_hint_skips_classification() -> None:
    """Si se provee intent_hint, no se llama al classifier."""
    classifier = InMemoryLLMAdapter(canned_response="campus", embedding_dim=8)
    synthesis = InMemoryLLMAdapter(canned_response="respuesta", embedding_dim=8)

    service = ChatService(
        synthesis_llm=synthesis,
        store=InMemoryVectorStoreAdapter(dim=8),
        embedder=FakeEmbedder(),
        classifier_llm=classifier,
    )

    # Forzar intent RESEARCH directamente
    request = ChatRequest(query="prueba", intent_hint=Intent.RESEARCH)
    response = service.answer(request)

    assert response.intent == Intent.RESEARCH
    # El classifier no se llamó
    assert len(classifier.complete_calls) == 0
