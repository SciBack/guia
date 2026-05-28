# ADR-050 — AgentOrchestrator: loop agéntico multi-paso para GUIA

**Estado:** Propuesto — 2026-05-28
**Autor:** Alberto Sanchez / SciBack
**Dia de implementacion:** Dia 1 (modelos + loop + tests basicos)

---

## Contexto

El ChatService actual (chat.py) es un pipeline RAG de un solo paso: embed → search → synthesize.
Funciona bien para consultas directas pero falla en escenarios que requieren razonamiento multi-paso:

- Reformulacion de queries cuando la primera busqueda no da resultados utiles.
- Pedido de aclaracion antes de buscar cuando la query es demasiado vaga.
- Futuro: reranking, busqueda multi-fuente, decomposicion de preguntas complejas.

La arquitectura hexagonal del proyecto (ports + adapters) permite introducir un orquestador
sin romper el contrato externo de ChatService.

---

## Pregunta

Como estructuramos el razonamiento multi-paso del LLM sin acoplar el producto a
frameworks de agentes externos (LangChain, LangGraph, AutoGen)?

---

## Decision

Implementar AgentOrchestrator como clase Python pura con loop explicito.
El LLM elige acciones en cada iteracion emitiendo JSON con discriminated union.
El orquestador parsea, valida con Pydantic y ejecuta la herramienta.

### Decisiones especificas

1. **Async nativo:** `run()` es `async def`. `LLMPort.complete()` es sync — se envuelve
   con `asyncio.to_thread()` en `_ask_llm()`. No se cambia el contrato de LLMPort.

2. **Estrategia de prompt JSON:** el system prompt usa resumen en lenguaje natural
   mas 3 ejemplos one-shot (search->answer, clarify, refine->answer).
   NO se incluye el JSON schema completo — reduce tokens y es suficientemente claro
   para modelos como Qwen3 8B y Claude.

3. **Usuarios anonimos excluidos:** el bucket agente solo aplica a usuarios autenticados.
   Usuarios anonimos van siempre al pipeline legacy (ChatService.answer).
   Esto se implementa en Dia 3 al conectar AgentOrchestrator con ChatService.

4. **Sin frameworks externos:** ninguna dependencia en LangChain, LangGraph, instructor,
   ni ninguna libreria de agent framework. Solo Pydantic + asyncio.

---

## Estructura de acciones

```
AgentAction (discriminated union por campo "action"):
  - SearchAction       → busca en el indice
  - RefineSearchAction → busca con query mejorada (despues de 0 resultados)
  - RerankAction       → reordena candidatos (STUB en Dia 1)
  - AnswerAction       → respuesta final con citas
  - ClarifyAction      → pregunta de aclaracion al usuario
```

Todas las acciones son `frozen=True` (inmutables). El envelope `AgentActionEnvelope`
tiene `extra="forbid"` para detectar alucinaciones del LLM fuera del schema.

---

## Loop principal

```
build messages (system + history + user_query)
for iteration in 1..max_iter:
    log debug: msg_count, total_chars   # observabilidad sin truncar
    action = await _ask_llm(messages)   # 1 retry en ValidationError
    if AnswerAction → return OrchestratorResult(fallback=False, forced_synthesis=False)
    if ClarifyAction → return OrchestratorResult(is_clarification=True)
    tool_result, new_records = await _execute_action(action)  # no muta estado
    tool_results_by_id.update(new_records)
    messages += [assistant_action_json, user_observation]
→ (agotado sin Answer) _force_final_synthesis
    instruccion final como role="system" (anti-eco JSON)
    si LLM emite JSON-like → descartado → fallback=True, forced_synthesis=True
    si LLM emite texto → fallback=False, forced_synthesis=True
→ (ValidationError x2) _fallback_direct_answer(fallback=True, forced_synthesis=False)
    query del usuario envuelta en <user_query>...</user_query> (anti prompt-injection)
```

Semantica de flags en OrchestratorResult:
- fallback=False, forced_synthesis=False: respuesta normal con AnswerAction o ClarifyAction
- fallback=False, forced_synthesis=True: sintesis al agotar max_iter, texto natural valido
- fallback=True, forced_synthesis=True: sintesis forzada pero el LLM emitio JSON (degradacion estatica)
- fallback=True, forced_synthesis=False: ValidationError irrecuperable, _fallback_direct_answer

Citations filtradas: solo doc_ids que existen en tool_results_by_id (normalizados con strip()).

---

## Consecuencias

**Positivas:**
- Control total del loop sin magia de framework.
- Traza de iteraciones (AgentTraceEntry) para observabilidad y debugging.
- Facil de testear: QueuedLLMAdapter + FakeSearchService, sin mocks.
- Aislado de ChatService hasta Dia 3 — cero riesgo en produccion hoy.

**Negativas:**
- El loop manual es mas verboso que un framework declarativo.
- RerankAction es un stub — el reranking real requiere cross-encoder (H2).
- Cada iteracion paga una llamada al LLM; max_iter=3 significa 3x latencia maxima.

---

## Criterio de exito A/B (a medir en Dia 3+)

| Metrica | Baseline (pipeline actual) | Target agente |
|---|---|---|
| NDCG@5 | 0.713 | >= 0.78 |
| Tasa de respuestas "no encontre nada" | ~12% | <= 6% |
| Latencia p95 | ~1.8s | <= 3.5s (acepta overhead de multi-paso) |
| Tasa de fallback del agente | — | <= 5% |

Rollout controlado via `GUIA_AGENT_MODE_ROLLOUT_PCT` (0-100%).

---

## Plan de retirada de router.py

router.py (ModelRouter) seguira operativo durante la transicion agente.
Cuando el agente alcance los criterios de exito A/B y cubra el 100% del rollout:

1. Remover la inyeccion de ModelRouter en GUIAContainer.
2. Deprecar ModelRouter con aviso en docstring.
3. Eliminar router.py en el sprint siguiente si no hay regresion.

---

## Settings nuevos

```
GUIA_AGENT_MODE_ENABLED     bool   default=False  — habilita el bucket agente
GUIA_AGENT_MODE_ROLLOUT_PCT int    default=0      — % de usuarios en el bucket
GUIA_AGENT_MAX_ITER         int    default=3      — max iteraciones por query
```

---

## Referencias

- ADR-028: LLMPort sync contract
- ADR-029: SearchService / OpenSearch backend
- ADR-044: Pipeline NLP (query rewriting)
- ADR-045: Gates router (LanguageGate, ToxicityGate)
- Memoria: `decisiones_arquitectura_llm.md` — decision LlamaIndex Workflows (H2)
- Memoria: `project_p3_retrieval.md` — NDCG@5 baseline = 0.713
