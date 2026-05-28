"""Tests del AgentOrchestrator — Dia 1 (ADR-050).

Cubre los 3 casos obligatorios del Dia 1:
1. search -> answer exitoso
2. clarify retorna inmediatamente
3. citation con doc_id inventado es descartada
"""

from __future__ import annotations

import json
from collections import deque

import pytest
from sciback_core.ports.llm import LLMMessage, LLMResponse
from sciback_core.ports.vector_store import VectorRecord

from guia.services.agent_orchestrator import AgentOrchestrator

# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


def _make_record(doc_id: str, title: str = "Titulo de prueba") -> VectorRecord:
    """Crea un VectorRecord minimo para tests."""
    return VectorRecord(
        id=doc_id,
        vector=[0.1, 0.2, 0.3],
        metadata={"title": title, "authors": ["Autor Prueba"], "year": 2023},
        score=0.85,
    )


def _search_json(query: str = "test query", max_results: int = 5) -> str:
    """JSON de SearchAction valido."""
    return json.dumps({
        "action_payload": {
            "action": "search",
            "query": query,
            "max_results": max_results,
        }
    })


def _answer_json(content: str = "Esta es la respuesta.", doc_ids: list[str] | None = None) -> str:
    """JSON de AnswerAction valido."""
    citations = [{"doc_id": d} for d in (doc_ids or [])]
    return json.dumps({
        "action_payload": {
            "action": "answer",
            "content": content,
            "citations": citations,
        }
    })


def _clarify_json(question: str = "?Sobre que tema exactamente?") -> str:
    """JSON de ClarifyAction valido."""
    return json.dumps({
        "action_payload": {
            "action": "clarify",
            "question": question,
        }
    })


class QueuedLLMAdapter:
    """Adaptador LLM con cola de respuestas predefinidas para tests.

    Consume una respuesta canned de la cola por cada llamada a complete().
    Si la cola se agota, retorna la ultima respuesta definida (o string vacio).

    Args:
        responses: Lista de strings JSON que se devolveran en orden.
    """

    DEFAULT_MODEL = "stub-model"

    def __init__(self, responses: list[str]) -> None:
        self._queue: deque[str] = deque(responses)
        self._last: str = responses[-1] if responses else ""
        self.complete_calls: list[list[LLMMessage]] = []

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Retorna la siguiente respuesta de la cola."""
        self.complete_calls.append(list(messages))
        content = self._queue.popleft() if self._queue else self._last
        return LLMResponse(
            content=content,
            model=model or self.DEFAULT_MODEL,
            input_tokens=sum(len(m.content.split()) for m in messages),
            output_tokens=len(content.split()),
        )

    def embed(self, texts: list[str], *, model: str | None = None):
        raise NotImplementedError("embed no usado en tests de orquestador")


class FakeSearchService:
    """SearchService fake que devuelve resultados predefinidos para tests.

    Args:
        records: Lista de VectorRecord a retornar en cada llamada a search().
    """

    def __init__(self, records: list[VectorRecord]) -> None:
        self._records = records
        self.search_calls: list[str] = []

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        min_score: float = 0.0,
        filter: dict | None = None,
    ) -> list[VectorRecord]:
        """Retorna todos los records predefinidos (hasta limit)."""
        self.search_calls.append(query)
        return self._records[:limit]


# ---------------------------------------------------------------------------
# Tests obligatorios Dia 1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_search_then_answer():
    """LLM emite SearchAction luego AnswerAction: 2 iteraciones, sources no vacios, no fallback."""
    doc_id = "koha:101"
    record = _make_record(doc_id, "Estadistica aplicada")

    llm = QueuedLLMAdapter([
        _search_json("estadistica aplicada"),
        _answer_json("Encontre un libro de estadistica.", doc_ids=[doc_id]),
    ])
    search = FakeSearchService([record])

    orchestrator = AgentOrchestrator(llm, search, max_iter=3)
    result = await orchestrator.run(
        query="libros de estadistica",
        history=[],
        privacy_verdict=None,
    )

    assert result.iterations == 2
    assert result.fallback is False
    assert result.is_clarification is False
    assert len(result.sources) == 1
    assert result.sources[0].id == doc_id
    assert len(result.trace) == 2
    assert result.trace[0].action == "search"
    assert result.trace[1].action == "answer"
    assert "estadistica" in result.answer.lower()


@pytest.mark.asyncio
async def test_clarify_returns_immediately():
    """LLM emite ClarifyAction en primer turno: 1 iteracion, is_clarification=True."""
    llm = QueuedLLMAdapter([
        _clarify_json("?Sobre que tema buscas libros?"),
    ])
    search = FakeSearchService([])

    orchestrator = AgentOrchestrator(llm, search, max_iter=3)
    result = await orchestrator.run(
        query="libros",
        history=[],
        privacy_verdict=None,
    )

    assert result.iterations == 1
    assert result.is_clarification is True
    assert result.fallback is False
    assert result.sources == []
    assert len(result.trace) == 1
    assert result.trace[0].action == "clarify"
    assert "tema" in result.answer.lower()


@pytest.mark.asyncio
async def test_invented_citation_id_is_stripped():
    """LLM cita doc_id='fake:999' que NO existe en resultados: sources debe estar vacio."""
    real_doc_id = "koha:200"
    record = _make_record(real_doc_id, "Libro real existente")

    llm = QueuedLLMAdapter([
        _search_json("libro real"),
        # El LLM cita un ID que NO fue retornado por la busqueda
        _answer_json("Respuesta con cita inventada.", doc_ids=["fake:999"]),
    ])
    search = FakeSearchService([record])

    orchestrator = AgentOrchestrator(llm, search, max_iter=3)
    result = await orchestrator.run(
        query="busca algo",
        history=[],
        privacy_verdict=None,
    )

    assert result.fallback is False
    assert result.is_clarification is False
    # La cita fake:999 no existe en tool_results_by_id -> debe ser descartada
    assert result.sources == [], (
        f"Se esperaba sources vacio, se obtuvo: {[s.id for s in result.sources]}"
    )
