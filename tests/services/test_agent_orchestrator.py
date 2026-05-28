"""Tests del AgentOrchestrator — Dia 1 y Dia 2 (ADR-050).

Cubre los 3 casos obligatorios del Dia 1:
1. search -> answer exitoso
2. clarify retorna inmediatamente
3. citation con doc_id inventado es descartada (ajustado Dia 2: fallback a tool_results)

Cubre los 5 casos nuevos del Dia 2 + 1 bonus:
4. JSON invalido en primer intento -> retry recupera con JSON valido
5. JSON invalido dos veces seguidas -> fallback_direct_answer
6. JSON valido pero action desconocida -> ValidationError -> fallback
7. LLM emite SearchAction infinitamente -> max_iter agotado -> force_synthesis
8. SearchService lanza RuntimeError -> observation de error -> orquestador no crashea
9. (bonus) privacy_verdict con force_local=True -> system prompt menciona privacidad
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
        """Retorna la siguiente respuesta de la cola.

        Fix 6: input_tokens es heuristico (conteo de palabras), NO tokenizacion real.
        No hacer asserts sobre valores exactos de tokens en los tests.
        """
        self.complete_calls.append(list(messages))
        content = self._queue.popleft() if self._queue else self._last
        return LLMResponse(
            content=content,
            model=model or self.DEFAULT_MODEL,
            # Heuristic: word count, NOT real tokenization. Don't assert on exact token counts.
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
    """LLM cita doc_id='fake:999' que NO existe en resultados.

    Comportamiento esperado (Dia 2):
    - 'fake:999' no debe aparecer en sources (citation inventada descartada).
    - Como no hay ninguna citation valida pero si hay tool_results, el fallback
      de _filter_valid_sources devuelve todos los tool_results reales.
    """
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
    # La cita fake:999 no existe -> descartada. No hay citas validas pero
    # hay tool_results -> _filter_valid_sources devuelve todos los reales.
    source_ids = [s.id for s in result.sources]
    assert "fake:999" not in source_ids, f"ID inventado no debe estar en sources: {source_ids}"
    assert real_doc_id in source_ids, (
        f"El doc real {real_doc_id} debe estar en sources (fallback a tool_results): {source_ids}"
    )


# ---------------------------------------------------------------------------
# Tests Dia 2 — robustez y comportamientos nuevos
# ---------------------------------------------------------------------------


def _invalid_json_response() -> str:
    """Respuesta que no es JSON valido (texto plano)."""
    return "Lo siento, no entendi el formato solicitado. Puedo ayudarte buscando libros."


def _unknown_action_json() -> str:
    """JSON valido estructuralmente pero con action no reconocida por el schema."""
    return json.dumps({
        "action_payload": {
            "action": "delete_db",
            "target": "all_records",
        }
    })


@pytest.mark.asyncio
async def test_invalid_json_one_retry_recovers():
    """LLM responde texto plano primero, luego AnswerAction valida.

    El retry interno de _ask_llm debe recuperar en el segundo intento.
    El resultado no debe ser fallback y el loop ve exactamente 1 iteracion exitosa.
    """
    doc_id = "koha:301"
    record = _make_record(doc_id, "Libro recuperado tras retry")

    llm = QueuedLLMAdapter([
        _invalid_json_response(),   # primer intento en _ask_llm -> parse error
        _answer_json("Respuesta recuperada tras retry.", doc_ids=[doc_id]),  # segundo intento
    ])
    search = FakeSearchService([record])

    orchestrator = AgentOrchestrator(llm, search, max_iter=3)
    result = await orchestrator.run(
        query="libros de administracion",
        history=[],
        privacy_verdict=None,
    )

    assert result.fallback is False, "El retry interno no debe disparar fallback"
    assert result.answer != "", "Debe haber respuesta"
    # El loop solo ve 1 iteracion: la que termino con AnswerAction
    assert result.iterations == 1
    # El LLM fue llamado 2 veces: intento 1 (fallo) + intento 2 (exito)
    assert len(llm.complete_calls) == 2


@pytest.mark.asyncio
async def test_invalid_json_two_failures_falls_back():
    """LLM responde texto plano en ambos intentos de _ask_llm.

    Debe activar _fallback_direct_answer: result.fallback=True, answer no vacio.
    """
    fallback_answer = "Esta es la respuesta directa del fallback."

    llm = QueuedLLMAdapter([
        _invalid_json_response(),  # intento 1 de _ask_llm -> parse error
        _invalid_json_response(),  # intento 2 de _ask_llm -> parse error -> re-raise
        fallback_answer,           # _fallback_direct_answer hace una llamada libre
    ])
    search = FakeSearchService([])

    orchestrator = AgentOrchestrator(llm, search, max_iter=3)
    result = await orchestrator.run(
        query="que libros hay sobre pedagogia",
        history=[],
        privacy_verdict=None,
    )

    assert result.fallback is True, "Dos fallos seguidos deben activar fallback"
    assert result.answer != "", "fallback_direct_answer debe proveer respuesta no vacia"
    # No debe crashear
    assert result.is_clarification is False


@pytest.mark.asyncio
async def test_unknown_action_discriminator():
    """LLM emite JSON valido pero con action desconocida ('delete_db').

    ValidationError en discriminated union -> retry interno -> si segundo
    intento tambien falla, activa fallback.
    """
    fallback_answer = "Respuesta directa tras action invalida."

    llm = QueuedLLMAdapter([
        _unknown_action_json(),    # intento 1 -> ValidationError (discriminator)
        _unknown_action_json(),    # intento 2 -> ValidationError -> re-raise
        fallback_answer,           # _fallback_direct_answer
    ])
    search = FakeSearchService([])

    orchestrator = AgentOrchestrator(llm, search, max_iter=3)
    result = await orchestrator.run(
        query="borrar todo",
        history=[],
        privacy_verdict=None,
    )

    assert result.fallback is True, "Action invalida debe terminar en fallback"
    assert result.answer != ""


@pytest.mark.asyncio
async def test_max_iter_cap_forces_synthesis():
    """LLM emite SearchAction en cada iteracion hasta agotar max_iter.

    Verifica:
    - El orquestador llama al LLM exactamente max_iter veces en el loop
      mas 1 llamada adicional de _force_final_synthesis.
    - El resultado viene de force_synthesis (fallback=False, iterations=max_iter).
    - Las sources contienen los doc_ids acumulados.
    """
    max_iter = 2
    doc_id_1 = "koha:401"
    doc_id_2 = "ojs:402"
    records = [
        _make_record(doc_id_1, "Libro 1"),
        _make_record(doc_id_2, "Articulo 2"),
    ]
    synthesis_text = "Sintesis final: encontre 2 documentos relevantes."

    # max_iter SearchActions + 1 llamada de synthesis
    llm = QueuedLLMAdapter([
        _search_json("query iter 1"),
        _search_json("query iter 2"),
        synthesis_text,  # _force_final_synthesis llama al LLM en texto libre
    ])
    search = FakeSearchService(records)

    orchestrator = AgentOrchestrator(llm, search, max_iter=max_iter)
    result = await orchestrator.run(
        query="busca documentos sobre educacion",
        history=[],
        privacy_verdict=None,
    )

    # max_iter iteraciones de search + 1 llamada de force_synthesis
    assert len(llm.complete_calls) == max_iter + 1, (
        f"Esperado {max_iter + 1} llamadas al LLM, got {len(llm.complete_calls)}"
    )
    assert result.iterations == max_iter
    assert result.fallback is False, "_force_final_synthesis con texto valido no es fallback"
    assert result.forced_synthesis is True, (
        "Al agotar max_iter el resultado debe tener forced_synthesis=True"
    )
    # Las sources deben contener los docs acumulados
    source_ids = {s.id for s in result.sources}
    assert doc_id_1 in source_ids
    assert doc_id_2 in source_ids


@pytest.mark.asyncio
async def test_search_service_failure_recovers():
    """SearchService lanza RuntimeError en cada llamada.

    El orquestador debe:
    - Capturar el error y reinyectar observation con mensaje de error.
    - NO crashear (no propagar la excepcion al caller).
    - Permitir que el LLM emita AnswerAction a continuacion.
    """
    class FailingSearchService:
        """SearchService que siempre lanza RuntimeError."""

        def search(self, query: str, *, limit: int = 5, **kwargs):
            raise RuntimeError("OpenSearch connection refused")

    llm = QueuedLLMAdapter([
        _search_json("educacion"),
        # El LLM decide responder a pesar de no tener resultados
        _answer_json("No encontre resultados disponibles en este momento.", doc_ids=[]),
    ])

    orchestrator = AgentOrchestrator(llm, FailingSearchService(), max_iter=3)  # type: ignore[arg-type]
    result = await orchestrator.run(
        query="libros sobre educacion primaria",
        history=[],
        privacy_verdict=None,
    )

    # No debe crashear
    assert result is not None
    assert result.fallback is False
    assert result.answer != ""
    # El mensaje de observation al LLM debe mencionar el error
    # (verificar en el historial de llamadas al LLM)
    # La segunda llamada debe contener "error" en algun message
    second_call_messages = llm.complete_calls[1]
    all_content = " ".join(m.content.lower() for m in second_call_messages)
    assert "error" in all_content, (
        "La observation reinyectada debe indicar el error al LLM"
    )


@pytest.mark.asyncio
async def test_force_local_privacy_verdict_in_system_prompt():
    """privacy_verdict con force_local=True genera system prompt con aviso de privacidad.

    Verifica que el contenido del system prompt enviado al LLM contiene
    texto relacionado con privacidad/datos personales.
    """
    from sciback_privacy import DataLevel, PrivacyVerdict

    doc_id = "koha:601"
    record = _make_record(doc_id, "Expediente academico")

    llm = QueuedLLMAdapter([
        _answer_json("Respuesta con aviso de privacidad.", doc_ids=[doc_id]),
    ])
    search = FakeSearchService([record])

    verdict = PrivacyVerdict(
        final_level=DataLevel.L2_PERSONAL,
        force_local=True,
        pii_in_query=True,
        reason="DNI detectado en query",
    )

    orchestrator = AgentOrchestrator(llm, search, max_iter=3)
    result = await orchestrator.run(
        query="busca tesis del estudiante con DNI 12345678",
        history=[],
        privacy_verdict=verdict,
    )

    assert result is not None
    # El system prompt (primer message de la primera llamada) debe mencionar privacidad
    first_call_messages = llm.complete_calls[0]
    system_msg = next((m for m in first_call_messages if m.role == "system"), None)
    assert system_msg is not None, "Debe existir un message de sistema"
    content_lower = system_msg.content.lower()
    has_privacy_mention = "privacidad" in content_lower or "personal" in content_lower
    assert has_privacy_mention, (
        f"System prompt debe mencionar privacidad con force_local=True:"
        f" {system_msg.content[:200]}"
    )


# ---------------------------------------------------------------------------
# Test Dia 3 — cascada real (Fix 7)
# ---------------------------------------------------------------------------


def _refine_json(new_query: str = "termino alternativo") -> str:
    """JSON de RefineSearchAction valido."""
    return json.dumps({
        "action_payload": {
            "action": "refine_search",
            "new_query": new_query,
            "reason": "La busqueda anterior no devolvio resultados utiles",
        }
    })


@pytest.mark.asyncio
async def test_cascade_search_refine_search_answer():
    """Cascada real: SearchAction -> RefineSearchAction -> SearchAction -> AnswerAction.

    Verifica:
    - iterations == 4 (una por cada accion emitida por el LLM antes de AnswerAction
      que cierra en la iteracion 4 del loop principal).
    - tool_results_by_id acumula records de los 2 search distintos.
    - trace contiene las 4 acciones en orden: search, refine_search, search, answer.
    - forced_synthesis=False (termino con AnswerAction real, no force_synthesis).
    - fallback=False.
    """
    doc_id_first = "koha:701"
    doc_id_second = "ojs:702"
    record_first = _make_record(doc_id_first, "Resultado primera busqueda")
    record_second = _make_record(doc_id_second, "Resultado segunda busqueda")

    # SearchService con respuestas distintas por llamada:
    # llamada 1 (iter 1, SearchAction) -> record_first
    # llamada 2 (iter 2, RefineSearchAction ejecuta busqueda) -> record_second
    # llamada 3 (iter 3, SearchAction) -> record_second (misma query refinada)
    # Total: 3 llamadas a search para 4 iteraciones del loop (la 4a es AnswerAction)
    class MultiPhaseSearchService:
        """Devuelve record_first en la primera llamada, record_second en las siguientes."""

        def __init__(self) -> None:
            self.search_calls: list[str] = []

        def search(self, query: str, *, limit: int = 5, **kwargs) -> list[VectorRecord]:
            self.search_calls.append(query)
            if len(self.search_calls) == 1:
                return [record_first]
            return [record_second]

    multi_phase_search = MultiPhaseSearchService()

    llm = QueuedLLMAdapter([
        _search_json("primera query sobre educacion"),            # iter 1: SearchAction
        _refine_json("segunda query refinada educacion Peru"),    # iter 2: RefineSearchAction
        _search_json("segunda query refinada educacion Peru"),    # iter 3: SearchAction
        _answer_json(                                            # iter 4: AnswerAction
            "Encontre documentos en ambas busquedas.",
            doc_ids=[doc_id_first, doc_id_second],
        ),
    ])

    orchestrator = AgentOrchestrator(llm, multi_phase_search, max_iter=5)
    result = await orchestrator.run(
        query="tesis sobre educacion en Peru",
        history=[],
        privacy_verdict=None,
    )

    # Termino con AnswerAction — no debe ser fallback ni forced_synthesis
    assert result.fallback is False, "Cascada que termina con Answer no es fallback"
    assert result.forced_synthesis is False, (
        "Cascada que termina con Answer no activa forced_synthesis"
    )
    assert result.is_clarification is False

    # 4 iteraciones: search, refine_search, search, answer
    assert result.iterations == 4, (
        f"Esperado 4 iteraciones en cascada, got {result.iterations}"
    )

    # Traza con las 4 acciones en orden correcto
    assert len(result.trace) == 4, f"Esperado 4 entradas en trace, got {len(result.trace)}"
    assert result.trace[0].action == "search"
    assert result.trace[1].action == "refine_search"
    assert result.trace[2].action == "search"
    assert result.trace[3].action == "answer"

    # Sources acumula records de las busquedas distintas
    source_ids = {s.id for s in result.sources}
    assert doc_id_first in source_ids, (
        f"doc_id de primera busqueda debe estar en sources: {source_ids}"
    )
    assert doc_id_second in source_ids, (
        f"doc_id de segunda busqueda debe estar en sources: {source_ids}"
    )

    # 3 llamadas a search: iter1 (SearchAction) + iter2 (RefineSearchAction) + iter3 (SearchAction)
    assert len(multi_phase_search.search_calls) == 3, (
        f"Esperado 3 llamadas a search (Search+Refine+Search), "
        f"got {len(multi_phase_search.search_calls)}"
    )
