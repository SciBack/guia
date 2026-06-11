# ADR-051 — Sidecar de embeddings compartido

**Fecha:** 2026-06-11 · **Estado:** Aceptado · **Decisores:** Alberto + review (architect-reviewer, code-reviewer)

## Contexto

api, chainlit, telegram y celery-workers cargaban cada uno su propia copia
in-process de fastembed `intfloat/multilingual-e5-large` (~2.5GB ONNX). En la
VM UPeU (9.7GB RAM) las copias simultáneas saturaron RAM+swap: queries de 5s
→ 62s por thrashing y un OOM-kill del api documentado (2026-06-11). El cold-
start del lazy-load (~60s) además producía 504 de nginx en la primera query
tras cada deploy.

## Decisión

Un servicio compose `embeddings` (sidecar) carga el modelo **una sola vez** y
lo sirve por HTTP emulando el endpoint Ollama `POST /api/embeddings`
(`{"model","prompt"}` → `{"embedding":[...]}`). Los canales consumen vía el
`E5EmbeddingAdapter` existente de sciback-core — el switch es solo `.env`:
`EMBEDDING_BACKEND=ollama` + `E5_OLLAMA_BASE_URL=http://embeddings:11434`.
Sin código nuevo en los canales, sin rebuild (reutiliza `image: guia-api`).

### Paridad de vectores (restricción dura)

- **Checkpoint canónico = el del índice:** `intfloat/multilingual-e5-large`
  vía fastembed ONNX (default de `FastEmbedConfig`). El índice pgvector/
  OpenSearch (35K docs) se construyó con él (`EMBEDDING_BACKEND=fastembed`
  en la VM + warning del modelo en logs del api).
- El cliente E5 antepone `"query: "`/`"passage: "`; el sidecar usa prefijos
  vacíos y enruta por prefijo recibido al mismo método fastembed del path
  directo (`query_embed`/`embed`) → mismo string final + mismos pesos +
  mismo método = vectores idénticos.
- **Alternativa rechazada — Ollama del Mac Mini:** sirve el checkpoint
  `-instruct` (pesos distintos) → exigiría reindexar 35K docs, y agrega
  dependencia de red inter-subnet en cada query del chat.

### Salvaguardas (review 2026-06-11)

- `asyncio.Semaphore(1)` serializa la inferencia: la `InferenceSession` ONNX
  y los buffers de fastembed se comparten, y dos forwards simultáneos
  duplicarían el pico de RAM.
- `/health` responde 503 hasta que el modelo está cargado; `depends_on:
  service_healthy` en api/chainlit/telegram + `start_period: 180s`.
- Errores de inferencia → 500 con `detail` (el cliente lo expone en su
  `IntegrationError`).
- Truncado: el cliente Ollama corta a ~1750 chars antes de enviar; los chunks
  del pipeline parent-document caen por debajo, impacto práctico nulo.

## Consecuencias

- (+) ~2.5GB residentes una vez en lugar de N veces; recreates de canales sin
  cold-start de embeddings ni riesgo OOM; workers de harvest tampoco cargan copia.
- (−) SPOF nuevo: si el sidecar cae, la búsqueda falla en todos los canales.
  Mitigación: `restart: unless-stopped` + healthcheck (~60s blast radius).
  Aceptable en piloto; para multi-cliente, réplicas o alerta Telegram.
- (−) Deploy completo en frío espera ~60-90s a que el sidecar esté healthy.
- Deuda anotada: endpoint batch en el sidecar para harvests masivos (hoy 1
  request/texto, igual que el protocolo Ollama original; en red Docker
  interna el overhead es ~1ms/texto).
