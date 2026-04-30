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

async def test_answer_returns_chat_response() -> None:
    """answer() retorna un ChatResponse válido."""
    service = _make_service()
    request = ChatRequest(query="¿Qué tesis hay sobre IA?")
    response = await service.answer(request)

    assert isinstance(response, ChatResponse)
    assert response.answer == "Respuesta de prueba"
    assert isinstance(response.intent, Intent)


async def test_answer_research_intent_calls_llm() -> None:
    """Para intent RESEARCH, se llama al LLM de síntesis."""
    service = _make_service(intent_response="research")
    request = ChatRequest(query="tesis machine learning")
    response = await service.answer(request)

    assert response.intent == Intent.RESEARCH
    assert response.answer == "Respuesta de prueba"


async def test_answer_out_of_scope_no_llm_call() -> None:
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
    response = await service.answer(request)

    assert response.intent == Intent.OUT_OF_SCOPE
    # El LLM de síntesis NO debe haberse llamado
    assert len(synthesis.complete_calls) == 0


async def test_answer_campus_returns_unavailable_message() -> None:
    """Para CAMPUS, retorna mensaje de no disponible (Fase 0)."""
    service = _make_service(intent_response="campus")
    request = ChatRequest(query="¿Cuánto debo en biblioteca?")
    response = await service.answer(request)

    assert response.intent == Intent.CAMPUS
    assert "campus" in response.answer.lower() or "disponible" in response.answer.lower()


async def test_answer_uses_vector_store_results() -> None:
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

    await service.answer(ChatRequest(query="inteligencia artificial"))

    # El LLM de síntesis fue llamado con mensajes que incluyen el contexto
    assert len(synthesis.complete_calls) == 1
    system_msg = synthesis.complete_calls[0][0]
    assert system_msg.role == "system"


async def test_answer_with_cache_hit_returns_cached_response() -> None:
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
    response = await service.answer(ChatRequest(query="consulta repetida"))

    assert response.cached is True
    assert response.answer == "Respuesta desde caché"
    # El LLM NO debe haberse llamado
    service._synthesis_llm.complete_calls == []  # type: ignore[union-attr]


async def test_answer_with_cache_miss_sets_cache() -> None:
    """Con cache miss, la respuesta se almacena en caché."""
    mock_cache = MagicMock()
    mock_cache.get.return_value = None  # miss

    service = _make_service(cache=mock_cache, intent_response="general")
    await service.answer(ChatRequest(query="consulta nueva"))

    mock_cache.set.assert_called_once()


async def test_answer_without_cache_works() -> None:
    """ChatService funciona sin caché configurado."""
    service = _make_service(cache=None)
    response = await service.answer(ChatRequest(query="prueba sin caché"))
    assert isinstance(response, ChatResponse)


async def test_answer_sources_from_store() -> None:
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

    response = await service.answer(ChatRequest(query="blockchain universidad"))
    assert len(response.sources) >= 1
    assert response.sources[0].title == "Tesis sobre blockchain"


async def test_answer_intent_hint_skips_classification() -> None:
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
    response = await service.answer(request)

    assert response.intent == Intent.RESEARCH
    # El classifier no se llamó
    assert len(classifier.complete_calls) == 0


# ── Integración CascadeRouter (P1.2) ──────────────────────────────────────


async def test_privacy_router_forces_local_when_pii_in_query() -> None:
    """Si la query menciona PII personal, el LLM cloud (synthesis) NO se usa.

    GUARDRAIL CRÍTICO P2.2: 'mis notas' → force_local → fast_llm (local).
    """
    cloud_synthesis = InMemoryLLMAdapter(canned_response="cloud response", embedding_dim=8)
    local_fast = InMemoryLLMAdapter(canned_response="local response", embedding_dim=8)

    service = ChatService(
        synthesis_llm=cloud_synthesis,
        fast_llm=local_fast,
        store=InMemoryVectorStoreAdapter(dim=8),
        embedder=FakeEmbedder(),
        classifier_llm=InMemoryLLMAdapter(canned_response="research", embedding_dim=8),
    )

    response = await service.answer(ChatRequest(query="¿cuáles son mis notas?"))

    # El cloud synthesis NO debe haberse llamado
    assert len(cloud_synthesis.complete_calls) == 0
    # El local fast SÍ
    assert len(local_fast.complete_calls) == 1
    assert response.answer == "local response"


async def test_privacy_router_forces_local_when_dni_in_query() -> None:
    """DNI peruano (8 dígitos) en query → force_local."""
    cloud_synthesis = InMemoryLLMAdapter(canned_response="cloud", embedding_dim=8)
    local_fast = InMemoryLLMAdapter(canned_response="local", embedding_dim=8)

    service = ChatService(
        synthesis_llm=cloud_synthesis,
        fast_llm=local_fast,
        store=InMemoryVectorStoreAdapter(dim=8),
        embedder=FakeEmbedder(),
        classifier_llm=InMemoryLLMAdapter(canned_response="research", embedding_dim=8),
    )

    await service.answer(ChatRequest(query="mi DNI es 70123456 ayúdame"))
    assert len(cloud_synthesis.complete_calls) == 0
    assert len(local_fast.complete_calls) == 1


async def test_force_local_dominates_over_redaction() -> None:
    """Cuando privacy_verdict.force_local=True, NO redactamos — vamos a Ollama
    local que es infraestructura controlada. La redacción es solo para cloud.

    Verifica que con DNI en query, fast_llm (local) recibe el DNI literal,
    y synthesis_llm (cloud) no se llama.
    """
    cloud_synthesis = InMemoryLLMAdapter(canned_response="cloud", embedding_dim=8)
    local_fast = InMemoryLLMAdapter(canned_response="local", embedding_dim=8)

    service = ChatService(
        synthesis_llm=cloud_synthesis,
        fast_llm=local_fast,
        store=InMemoryVectorStoreAdapter(dim=8),
        embedder=FakeEmbedder(),
        classifier_llm=InMemoryLLMAdapter(canned_response="research", embedding_dim=8),
    )

    await service.answer(ChatRequest(query="busca tesis del autor DNI 70123456"))

    # Cloud nunca se llamó (force_local por DNI)
    assert len(cloud_synthesis.complete_calls) == 0
    # Local SÍ se llamó, y recibió el DNI literal (no redactado)
    assert len(local_fast.complete_calls) == 1
    user_msg = next(
        m for m in local_fast.complete_calls[0] if m.role == "user"
    )
    assert "70123456" in user_msg.content


async def test_pii_redaction_module_unit() -> None:
    """Verifica el contrato de redact()/restore() (la integración en cloud
    solo se prueba al ser exposed con store con PII en docs — fuera del
    alcance de un unit test, queda para integration tests con Postgres real).
    """
    from guia.privacy import redact, restore

    text = "Soy Juan, DNI 70123456, correo juan@upeu.edu.pe"
    d = redact(text)
    assert d.has_pii is True
    assert "70123456" not in d.redacted_text
    assert "juan@upeu.edu.pe" not in d.redacted_text

    # LLM responde con placeholder → restore re-hidrata
    fake_llm_resp = "Tu DNI <USER_DNI_1> y email <USER_EMAIL_1> están registrados."
    restored = restore(fake_llm_resp, d.replacements)
    assert "70123456" in restored
    assert "juan@upeu.edu.pe" in restored
    assert "<USER_" not in restored


async def test_privacy_router_allows_cloud_for_research_no_pii() -> None:
    """Query inocua de research → cloud_ok → synthesis_llm (no fast)."""
    cloud_synthesis = InMemoryLLMAdapter(canned_response="cloud", embedding_dim=8)
    local_fast = InMemoryLLMAdapter(canned_response="local", embedding_dim=8)

    service = ChatService(
        synthesis_llm=cloud_synthesis,
        fast_llm=local_fast,
        store=InMemoryVectorStoreAdapter(dim=8),
        embedder=FakeEmbedder(),
        classifier_llm=InMemoryLLMAdapter(canned_response="research", embedding_dim=8),
    )

    response = await service.answer(
        ChatRequest(query="¿qué tesis hay sobre teología sistemática?")
    )
    # Cloud synthesis llamado (research sin PII → cloud OK)
    assert len(cloud_synthesis.complete_calls) == 1
    assert response.answer == "cloud"


async def test_cascade_router_short_circuits_classifier_on_greeting() -> None:
    """Con CascadeRouter inyectado, un saludo se resuelve en Gate 1 sin LLM."""
    import asyncio as _asyncio

    from guia.routing import CascadeRouter, EmbeddingRouter, RuleBasedRouter
    from tests.unit.test_routing_embedding import FakeEmbedder as RouteFakeEmbedder

    classifier = InMemoryLLMAdapter(canned_response="research", embedding_dim=8)
    synthesis = InMemoryLLMAdapter(canned_response="hola, soy GUIA", embedding_dim=8)

    embedding_router = EmbeddingRouter(RouteFakeEmbedder())
    await embedding_router.warm_up()
    cascade = CascadeRouter(rules=RuleBasedRouter(), embedding=embedding_router)

    # Embedder de routing produce vectores de 4 dim, pero ChatService usa
    # el embedder de 8 dim que vino del FakeEmbedder local. Adapter:
    class BridgeEmbedder:
        embedding_dim = 8

        def embed_query(self, q: str) -> list[float]:
            return [0.1] * 8

        def embed_passages(self, texts: list[str]) -> object:
            from sciback_core.ports.llm import EmbeddingResponse
            return EmbeddingResponse(
                embeddings=[[0.1] * 8] * len(texts),
                model="bridge",
                input_tokens=0,
            )

    service = ChatService(
        synthesis_llm=synthesis,
        store=InMemoryVectorStoreAdapter(dim=8),
        embedder=BridgeEmbedder(),  # type: ignore[arg-type]
        classifier_llm=classifier,
        cascade_router=cascade,
    )

    # "hola" matchea Gate 1 → no llama al classifier_llm
    response = await service.answer(ChatRequest(query="hola"))

    assert response.intent == Intent.GENERAL  # GREETING → GENERAL legacy
    assert len(classifier.complete_calls) == 0  # CRÍTICO: ahorra latencia LLM
