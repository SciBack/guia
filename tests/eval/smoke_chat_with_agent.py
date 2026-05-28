"""Smoke test: wiring ChatService ↔ AgentOrchestrator ↔ AuditLog.

Verifica que la integración funciona sin APIs externas:
- ChatService con agent_mode_enabled=True, rollout_pct=100
- AgentOrchestrator con InMemoryLLMAdapter (responde JSON de answer)
- FakeSearchService (retorna VectorRecords estáticos)
- Audit capturado en memoria

Ejecutar:
    uv run --quiet python tests/eval/smoke_chat_with_agent.py
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from sciback_core.ports.llm import InMemoryLLMAdapter, LLMMessage
from sciback_core.ports.vector_store import InMemoryVectorStoreAdapter, VectorRecord

from guia.domain.chat import ChatRequest, Intent
from guia.services.agent_orchestrator import AgentOrchestrator
from guia.services.chat import ChatService


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeEmbedder:
    """Embedder stub — vectores de dim=8."""

    embedding_dim = 8

    def embed_query(self, query: str) -> list[float]:  # noqa: ARG002
        return [0.1] * 8

    def embed_passages(self, texts: list[str]) -> object:
        from sciback_core.ports.llm import EmbeddingResponse
        return EmbeddingResponse(
            embeddings=[[0.1] * 8] * len(texts),
            model="stub-e5",
            input_tokens=0,
        )


class FakeSearchService:
    """SearchService stub que retorna 2 VectorRecord fijos."""

    def search(self, query: str, *, limit: int = 10) -> list[VectorRecord]:  # noqa: ARG002
        return [
            VectorRecord(
                id="koha:001",
                vector=[0.1] * 8,
                metadata={
                    "title": "Estadística aplicada a la investigación",
                    "authors": ["Hernández, R."],
                    "year": 2019,
                    "source": "koha",
                },
                score=0.92,
            ),
            VectorRecord(
                id="ojs:088",
                vector=[0.1] * 8,
                metadata={
                    "title": "Machine learning en educación universitaria",
                    "authors": ["Torres, M."],
                    "year": 2022,
                    "source": "ojs",
                },
                score=0.87,
            ),
        ]


@dataclass
class FakeAuditRepo:
    """Audit repo en memoria para capturar entries del smoke test."""

    entries: list[Any] = field(default_factory=list)

    async def record(self, entry: object) -> None:
        self.entries.append(entry)


class FakeSettings:
    """Settings mínimo para activar el agente en el smoke test."""
    agent_mode_enabled = True
    agent_mode_rollout_pct = 100
    ojs_base_url = ""
    dspace_base_url = ""
    alicia_base_url = ""
    indico_base_url = ""
    dspace_indexed = False
    alicia_indexed = False


# ---------------------------------------------------------------------------
# Construir un InMemoryLLMAdapter que responde con JSON de AnswerAction
# ---------------------------------------------------------------------------


def _make_agent_llm() -> InMemoryLLMAdapter:
    """LLM que responde con una AnswerAction JSON válida."""
    answer_json = json.dumps({
        "action_payload": {
            "action": "answer",
            "content": "Encontré estos recursos relevantes para tu consulta académica.",
            "citations": [
                {"doc_id": "koha:001"},
                {"doc_id": "ojs:088"},
            ],
        }
    })
    # El orquestador hace primero search, luego answer.
    # InMemoryLLMAdapter usa una única respuesta canned — para el smoke
    # lo configuramos para que responda siempre con search la primera vez
    # y answer la segunda.  Usando deque en LLM con múltiples respuestas.
    search_json = json.dumps({
        "action_payload": {
            "action": "search",
            "query": "estadística investigación",
            "max_results": 5,
        }
    })
    # InMemoryLLMAdapter no soporta respuestas secuenciales —
    # para el smoke usamos directamente AnswerAction como única respuesta.
    # El orquestador lo parsea en el primer turno y retorna inmediatamente.
    return InMemoryLLMAdapter(canned_response=answer_json, embedding_dim=8)


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------


async def run_smoke() -> None:
    print("=== smoke_chat_with_agent.py ===\n")

    audit_repo = FakeAuditRepo()
    fake_search = FakeSearchService()
    agent_llm = _make_agent_llm()

    orchestrator = AgentOrchestrator(
        llm=agent_llm,
        search=fake_search,  # type: ignore[arg-type]
        max_iter=3,
        institution="UPeU (smoke test)",
    )

    service = ChatService(
        synthesis_llm=InMemoryLLMAdapter(canned_response="fallback legacy", embedding_dim=8),
        store=InMemoryVectorStoreAdapter(dim=8),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        classifier_llm=InMemoryLLMAdapter(canned_response="research", embedding_dim=8),
        settings=FakeSettings(),  # type: ignore[arg-type]
        agent_orchestrator=orchestrator,
        audit_repo=audit_repo,  # type: ignore[arg-type]
    )

    queries = [
        ("tesis sobre estadística para investigación", "user-smoke-001", Intent.RESEARCH),
        ("libros de machine learning", "user-smoke-002", Intent.GENERAL),
        ("artículos de nutrición infantil", "user-smoke-003", Intent.RESEARCH),
    ]

    for query_text, user_id, intent_hint in queries:
        print(f"Query: {query_text!r}")
        request = ChatRequest(
            query=query_text,
            user_id=user_id,
            intent_hint=intent_hint,
        )
        response = await service.answer(request)
        print(f"  model_used : {response.model_used}")
        print(f"  answer     : {response.answer[:80]}...")
        print(f"  sources    : {[s.id for s in response.sources]}")
        print()

    print(f"Audit entries capturadas: {len(audit_repo.entries)}")
    for e in audit_repo.entries:
        print(f"  orchestrator_mode    : {e.orchestrator_mode}")
        print(f"  agent_iterations     : {e.agent_iterations}")
        print(f"  agent_actions        : {e.agent_actions}")
        print(f"  agent_fallback       : {e.agent_fallback}")
        print(f"  agent_forced_synth   : {e.agent_forced_synthesis}")
        print()

    # Validaciones básicas
    for e in audit_repo.entries:
        assert e.orchestrator_mode == "agent", f"Expected 'agent', got {e.orchestrator_mode!r}"
        assert e.agent_iterations is not None and e.agent_iterations >= 1
        assert e.agent_actions is not None and len(e.agent_actions) >= 1

    print("OK — todas las validaciones pasaron.")


if __name__ == "__main__":
    asyncio.run(run_smoke())
