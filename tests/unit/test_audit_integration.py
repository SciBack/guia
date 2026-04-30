"""Tests de integración audit con ChatService (P1.3 paso 2).

Verifica que cada query a ChatService.answer() emite una entrada de audit
con el contenido correcto y SIN la query original."""

from __future__ import annotations

from sciback_core.ports.llm import InMemoryLLMAdapter
from sciback_core.ports.vector_store import InMemoryVectorStoreAdapter

from guia.audit import AuditLogEntry, AuditLogRepository, hash_query
from guia.domain.chat import ChatRequest, Intent
from guia.services.chat import ChatService


# ── Fake repository en memoria ────────────────────────────────────────────


class InMemoryAuditRepo(AuditLogRepository):
    """Repo de audit que no toca Postgres — lista en memoria."""

    def __init__(self) -> None:
        # No llamamos a super().__init__ porque no queremos abrir conexión
        self._url = ""
        self._conn = None
        self.entries: list[AuditLogEntry] = []

    async def record(self, entry: AuditLogEntry) -> None:
        self.entries.append(entry)


class FakeEmbedder:
    embedding_dim = 8

    def embed_query(self, q: str) -> list[float]:
        return [0.1] * 8

    def embed_passages(self, texts: list[str]) -> object:
        from sciback_core.ports.llm import EmbeddingResponse
        return EmbeddingResponse(embeddings=[[0.1] * 8] * len(texts), model="fake", input_tokens=0)


def _make_service(audit_repo: AuditLogRepository | None) -> ChatService:
    return ChatService(
        synthesis_llm=InMemoryLLMAdapter(canned_response="respuesta", embedding_dim=8),
        store=InMemoryVectorStoreAdapter(dim=8),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        classifier_llm=InMemoryLLMAdapter(canned_response="research", embedding_dim=8),
        audit_repo=audit_repo,
    )


# ── REGLA CRÍTICA: la query original NO se persiste ───────────────────────


async def test_audit_persists_only_hash_not_query() -> None:
    """La query 'información súper sensible' NO aparece en el audit; solo el hash."""
    audit = InMemoryAuditRepo()
    service = _make_service(audit_repo=audit)

    raw_query = "información súper sensible sobre mis notas"
    await service.answer(ChatRequest(query=raw_query, user_id="alice"))

    assert len(audit.entries) == 1
    entry = audit.entries[0]
    assert entry.query_hash == hash_query(raw_query)
    # CRÍTICO: nada del texto original aparece en NINGÚN campo del entry
    blob = str(entry.__dict__)
    assert "súper sensible" not in blob
    assert "información" not in blob
    assert raw_query not in blob


# ── Una entrada por query ─────────────────────────────────────────────────


async def test_audit_emits_one_entry_per_query() -> None:
    audit = InMemoryAuditRepo()
    service = _make_service(audit_repo=audit)

    await service.answer(ChatRequest(query="query 1", user_id="alice"))
    await service.answer(ChatRequest(query="query 2", user_id="alice"))
    await service.answer(ChatRequest(query="query 3", user_id="bob"))

    assert len(audit.entries) == 3
    assert audit.entries[0].user_id == "alice"
    assert audit.entries[2].user_id == "bob"


# ── No-op cuando no hay repo ──────────────────────────────────────────────


async def test_chat_service_works_without_audit_repo() -> None:
    """Sin audit_repo configurado, todo sigue funcionando (compat)."""
    service = _make_service(audit_repo=None)
    response = await service.answer(ChatRequest(query="test"))
    assert response.intent in {Intent.RESEARCH, Intent.GENERAL, Intent.CAMPUS, Intent.OUT_OF_SCOPE}


# ── Provider detection ───────────────────────────────────────────────────


async def test_audit_records_provider_local_for_qwen() -> None:
    audit = InMemoryAuditRepo()
    # InMemoryLLMAdapter pone 'in-memory-llm' como model_name por default
    # Tenemos que ver cómo InMemoryLLMAdapter setea model en su response.
    # Para este test, forzamos via una respuesta con model_used patcheado.
    # Mejor: testeamos directamente _detect_llm_provider.
    from guia.services.chat import _detect_llm_provider

    assert _detect_llm_provider("qwen2.5:7b") == "ollama-local"
    assert _detect_llm_provider("qwen2.5:3b") == "ollama-local"
    assert _detect_llm_provider("deepseek-r1:distill") == "ollama-local"


async def test_audit_records_provider_cloud_for_claude() -> None:
    from guia.services.chat import _detect_llm_provider

    assert _detect_llm_provider("claude-haiku-4-5") == "anthropic-cloud"
    assert _detect_llm_provider("claude-sonnet-4-7") == "anthropic-cloud"


async def test_audit_records_provider_none_for_no_llm() -> None:
    from guia.services.chat import _detect_llm_provider

    assert _detect_llm_provider("none") == "none"
    assert _detect_llm_provider("") == "none"
    assert _detect_llm_provider("koha") == "none"


# ── Latency y session_id ──────────────────────────────────────────────────


async def test_audit_records_latency_ms() -> None:
    audit = InMemoryAuditRepo()
    service = _make_service(audit_repo=audit)

    await service.answer(ChatRequest(query="test", user_id="u"))

    assert len(audit.entries) == 1
    assert audit.entries[0].latency_ms >= 0


async def test_audit_records_session_id_when_provided() -> None:
    audit = InMemoryAuditRepo()
    service = _make_service(audit_repo=audit)

    await service.answer(
        ChatRequest(query="test", user_id="u", session_id="sess-abc")
    )

    assert audit.entries[0].session_id == "sess-abc"


async def test_audit_user_id_anonymous_when_missing() -> None:
    audit = InMemoryAuditRepo()
    service = _make_service(audit_repo=audit)

    await service.answer(ChatRequest(query="test"))

    assert audit.entries[0].user_id == "anonymous"


# ── Audit no rompe la respuesta cuando falla ─────────────────────────────


async def test_audit_failure_does_not_break_response() -> None:
    """Si record() lanza excepción, el usuario sigue recibiendo respuesta."""

    class BrokenRepo(AuditLogRepository):
        def __init__(self) -> None:
            self._url = ""
            self._conn = None

        async def record(self, entry: AuditLogEntry) -> None:
            raise RuntimeError("DB caído")

    service = _make_service(audit_repo=BrokenRepo())
    response = await service.answer(ChatRequest(query="test"))
    # El usuario SÍ recibe respuesta (no se propaga la excepción)
    assert response.answer == "respuesta"
