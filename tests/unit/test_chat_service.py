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
    from sciback_privacy import redact, restore

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


# ── Tests Día 3: AgentOrchestrator A/B (ADR-050) ─────────────────────────────


def _make_fake_settings(*, agent_mode_enabled: bool, rollout_pct: int = 100) -> object:
    """Crea un objeto de settings mínimo para tests del agente."""
    class _FakeSettings:
        agent_mode_enabled = False
        agent_mode_rollout_pct = 100
        ojs_base_url = ""
        dspace_base_url = ""
        alicia_base_url = ""
        indico_base_url = ""
        dspace_indexed = False
        alicia_indexed = False

    s = _FakeSettings()
    s.agent_mode_enabled = agent_mode_enabled
    s.agent_mode_rollout_pct = rollout_pct
    return s


async def test_chat_with_flag_off_uses_legacy_pipeline() -> None:
    """Test 10: flag OFF → pipeline legacy, orchestrator.run nunca llamado.

    Aunque se inyecte un orquestador, si agent_mode_enabled=False el ChatService
    debe usar el pipeline legacy y no invocar orchestrator.run.
    """
    from unittest.mock import AsyncMock, MagicMock

    from guia.services.agent_orchestrator import OrchestratorResult

    synthesis = InMemoryLLMAdapter(canned_response="respuesta legacy", embedding_dim=8)
    classifier = InMemoryLLMAdapter(canned_response="research", embedding_dim=8)

    fake_orchestrator = MagicMock()
    fake_orchestrator.run = AsyncMock(return_value=OrchestratorResult(
        answer="respuesta agente",
        sources=[],
        trace=[],
        iterations=1,
        fallback=False,
        forced_synthesis=False,
        is_clarification=False,
    ))

    service = ChatService(
        synthesis_llm=synthesis,
        store=InMemoryVectorStoreAdapter(dim=8),
        embedder=FakeEmbedder(),
        classifier_llm=classifier,
        settings=_make_fake_settings(agent_mode_enabled=False, rollout_pct=100),  # type: ignore[arg-type]
        agent_orchestrator=fake_orchestrator,  # type: ignore[arg-type]
    )

    response = await service.answer(
        ChatRequest(query="tesis sobre machine learning", user_id="user-123")
    )

    # El orquestador NO debe haberse llamado
    fake_orchestrator.run.assert_not_called()
    # La respuesta viene del pipeline legacy
    assert response.answer == "respuesta legacy"
    assert response.model_used != "agent"


async def test_chat_with_flag_on_and_rollout_100_uses_agent() -> None:
    """Test 11: flag ON + rollout=100 → orchestrator.run llamado, audit con métricas.

    Con intent=RESEARCH, user_id no anónimo, sin PII, flag ON y rollout=100,
    el ChatService debe delegar al orquestador y poblar el audit con los campos
    del agente.
    """
    from unittest.mock import AsyncMock, MagicMock

    from sciback_core.ports.vector_store import VectorRecord
    from guia.services.agent_orchestrator import AgentTraceEntry, OrchestratorResult

    _doc = VectorRecord(
        id="koha:101",
        vector=[0.1] * 8,
        metadata={"title": "Libro de prueba", "authors": ["Autor Test"], "year": 2024},
        score=0.9,
    )
    _trace = [AgentTraceEntry(iteration=1, action="search", tokens_in=10, tokens_out=5, latency_ms=100)]

    fake_orchestrator = MagicMock()
    fake_orchestrator.run = AsyncMock(return_value=OrchestratorResult(
        answer="Encontré este libro muy relevante.",
        sources=[_doc],
        trace=_trace,
        iterations=2,
        fallback=False,
        forced_synthesis=False,
        is_clarification=False,
    ))

    # Capturar la entry de audit para verificar los campos del agente
    audit_entries: list = []

    class _CapturingAuditRepo:
        async def record(self, entry: object) -> None:
            audit_entries.append(entry)

    service = ChatService(
        synthesis_llm=InMemoryLLMAdapter(canned_response="no debe usarse", embedding_dim=8),
        store=InMemoryVectorStoreAdapter(dim=8),
        embedder=FakeEmbedder(),
        classifier_llm=InMemoryLLMAdapter(canned_response="research", embedding_dim=8),
        settings=_make_fake_settings(agent_mode_enabled=True, rollout_pct=100),  # type: ignore[arg-type]
        agent_orchestrator=fake_orchestrator,  # type: ignore[arg-type]
        audit_repo=_CapturingAuditRepo(),  # type: ignore[arg-type]
    )

    response = await service.answer(
        ChatRequest(
            query="libros sobre estadística para tesis",
            user_id="user-123",
            intent_hint=Intent.RESEARCH,
        )
    )

    # El orquestador fue llamado exactamente una vez
    fake_orchestrator.run.assert_called_once()
    # La respuesta es la del orquestador
    assert response.answer == "Encontré este libro muy relevante."
    assert response.model_used == "agent"
    # Las fuentes se convierten correctamente
    assert len(response.sources) == 1
    assert response.sources[0].title == "Libro de prueba"
    # Audit contiene los campos del agente
    assert len(audit_entries) == 1
    entry = audit_entries[0]
    assert entry.orchestrator_mode == "agent"
    assert entry.agent_iterations == 2
    assert entry.agent_actions == ["search"]
    assert entry.agent_fallback is False
    assert entry.agent_forced_synthesis is False


async def test_chat_with_pii_l2l3_forces_legacy_even_if_agent_enabled() -> None:
    """Test 12: PII L2/L3 (force_local=True) → legacy aunque flag ON y rollout=100.

    GUARDRAIL CRÍTICO: datos personales no van al orquestador (que podría usar
    un LLM cloud). El pipeline legacy con fast_llm local es el camino correcto.
    """
    from unittest.mock import AsyncMock, MagicMock

    from guia.services.agent_orchestrator import OrchestratorResult

    cloud_synthesis = InMemoryLLMAdapter(canned_response="cloud response", embedding_dim=8)
    local_fast = InMemoryLLMAdapter(canned_response="local response", embedding_dim=8)

    fake_orchestrator = MagicMock()
    fake_orchestrator.run = AsyncMock(return_value=OrchestratorResult(
        answer="agente no deberia ejecutarse",
        sources=[],
        trace=[],
        iterations=1,
        fallback=False,
        forced_synthesis=False,
        is_clarification=False,
    ))

    service = ChatService(
        synthesis_llm=cloud_synthesis,
        fast_llm=local_fast,
        store=InMemoryVectorStoreAdapter(dim=8),
        embedder=FakeEmbedder(),
        classifier_llm=InMemoryLLMAdapter(canned_response="research", embedding_dim=8),
        settings=_make_fake_settings(agent_mode_enabled=True, rollout_pct=100),  # type: ignore[arg-type]
        agent_orchestrator=fake_orchestrator,  # type: ignore[arg-type]
    )

    # DNI en la query → PrivacyRouter detecta PII → force_local=True → legacy
    response = await service.answer(
        ChatRequest(
            query="busco tesis, mi DNI es 70123456",
            user_id="user-123",
        )
    )

    # El orquestador NO debe haberse llamado — PII obliga a legacy
    fake_orchestrator.run.assert_not_called()
    # El cloud synthesis tampoco — PII obliga a fast_llm local
    assert len(cloud_synthesis.complete_calls) == 0
    # El fast_llm local SÍ se llamó
    assert len(local_fast.complete_calls) == 1
    assert response.answer == "local response"


# ── answer_type + citas inline (listado vs narrativa) ──────────────────────────


def test_koha_opac_url_construye_link_desde_doc_id() -> None:
    """koha:<biblio> → URL del OPAC; otros prefijos o sin base → None."""
    from guia.services.chat import koha_opac_url

    base = "https://catalogo.upeu.edu.pe"
    assert koha_opac_url("koha:123", base) == (
        "https://catalogo.upeu.edu.pe/cgi-bin/koha/opac-detail.pl?biblionumber=123"
    )
    assert koha_opac_url("ojs:45", base) is None  # no es Koha
    assert koha_opac_url("koha:1", "") is None     # sin base configurada
    assert koha_opac_url("koha:", base) is None    # biblionumber vacío


def test_classify_answer_type_lista_vs_narrativa() -> None:
    """4+ resultados en intent de búsqueda → 'list'; si no → 'narrative'."""
    from guia.domain.chat import Intent, Source
    from guia.services.chat import _classify_answer_type

    many = [Source(id=f"koha:{i}", title=f"t{i}") for i in range(5)]
    few = many[:2]
    assert _classify_answer_type(Intent.RESEARCH, many) == "list"
    assert _classify_answer_type(Intent.GENERAL, many) == "list"
    assert _classify_answer_type(Intent.RESEARCH, few) == "narrative"
    assert _classify_answer_type(Intent.CAMPUS, many) == "narrative"  # no es búsqueda RAG


def test_render_results_list_enlaces_inline_sin_seccion_duplicada() -> None:
    """El listado pone cada ítem como enlace inline y no duplica 'Fuente consultada'."""
    from guia.channels.render import render_results_list
    from guia.domain.chat import ChatResponse, Intent, Source

    resp = ChatResponse(
        answer="Encontré estos libros: 1. Estadística 2. Metodología",
        intent=Intent.RESEARCH,
        model_used="agent",
        answer_type="list",
        sources=[
            Source(
                id="koha:1",
                title="Estadística aplicada",
                url="https://cat.upeu.edu.pe/opac/1",
                authors=["Hernández"],
                year=2019,
                source_type="koha",
            ),
            Source(id="koha:2", title="Metodología", url="https://cat.upeu.edu.pe/opac/2"),
        ],
    )
    out = render_results_list(resp)
    assert "[Estadística aplicada](https://cat.upeu.edu.pe/opac/1)" in out
    assert "[Metodología](https://cat.upeu.edu.pe/opac/2)" in out
    assert "Fuente consultada" not in out
    assert "2 resultados encontrados" in out
