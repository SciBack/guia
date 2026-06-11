"""Sidecar de embeddings — una sola copia del modelo para todos los canales.

Problema que resuelve: api, chainlit, telegram y workers cargaban cada uno su
propia copia de fastembed e5-large (~2.5GB). En la VM UPeU (9.7GB) las copias
simultáneas saturaban RAM+swap (queries de 5s → 62s por thrashing, OOM-kills).

Solución: este proceso carga el modelo UNA vez y lo sirve por HTTP emulando el
endpoint de Ollama (``POST /api/embeddings`` con ``{"model", "prompt"}`` →
``{"embedding": [...]}``), que es exactamente lo que habla el
``E5EmbeddingAdapter`` existente vía ``OllamaLLMAdapter``. Los canales solo
cambian config: ``EMBEDDING_BACKEND=ollama`` + ``E5_OLLAMA_BASE_URL`` → sidecar.

Paridad de vectores: el ``E5EmbeddingAdapter`` cliente ya antepone los prefijos
("query: " / "passage: "), así que aquí el adapter local se configura con
prefijos vacíos y se enruta por prefijo recibido al MISMO método fastembed que
usaba el path directo (``query_embed`` para queries, ``embed`` para passages).
Mismos pesos ONNX + mismo método + mismo string final = vectores idénticos al
índice pgvector/OpenSearch existente.

Despliegue: servicio compose ``embeddings`` reutilizando la imagen guia-api
(sin rebuild), comando::

    python -m uvicorn guia.embeddings_sidecar:app --host 0.0.0.0 --port 11434

Supuestos documentados (review 2026-06-11):
- El modelo canónico es el del índice: ``intfloat/multilingual-e5-large``
  (default de FastEmbedConfig; fijar FASTEMBED_MODEL en .env si cambia).
  NO usar el Ollama del Mac Mini como backend: sirve el checkpoint
  ``-instruct`` (pesos distintos) — rompería la paridad con el índice.
- El cliente OllamaLLMAdapter trunca a ~1750 chars antes de enviar; los
  passages largos de harvests futuros verán ese truncado además del de
  fastembed (512 tokens). Los chunks del pipeline (parent-document) caen
  por debajo, así que el impacto práctico es nulo; queda anotado.
- La inferencia se serializa con un semáforo: la sesión ONNX compartida no
  es segura ante Run() concurrente con los buffers de fastembed, y dos
  forwards simultáneos duplicarían el pico de RAM en la VM.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from guia.logging import configure_logging, get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = get_logger(__name__)

_QUERY_PREFIX = "query: "

# Una inferencia a la vez: la InferenceSession ONNX y los buffers de fastembed
# se comparten; además el pico de RAM por forward no debe multiplicarse.
_infer_sem = asyncio.Semaphore(1)


class _State:
    """Estado del proceso: el adapter se carga en el lifespan."""

    adapter: object | None = None
    ready: bool = False


_state = _State()


def _build_adapter() -> object:
    """FastEmbedAdapter con prefijos vacíos — el cliente ya los antepone."""
    from sciback_embeddings_fastembed import FastEmbedAdapter, FastEmbedConfig

    return FastEmbedAdapter(
        FastEmbedConfig(_env_file=None, query_prefix="", passage_prefix="")
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_logging(level="INFO", json_logs=True)
    logger.info("embeddings_sidecar_starting")
    _state.adapter = _build_adapter()
    # Cargar el modelo ONNX ya (no lazy): el healthcheck del contenedor pasa
    # recién cuando /health responde 200, y los dependientes esperan healthy.
    await asyncio.to_thread(_state.adapter.embed_query, "warmup")  # type: ignore[attr-defined]
    _state.ready = True
    logger.info("embeddings_sidecar_ready")
    yield
    logger.info("embeddings_sidecar_shutting_down")


app = FastAPI(title="GUIA Embeddings Sidecar", lifespan=lifespan)


class EmbeddingsRequest(BaseModel):
    """Forma del request de Ollama /api/embeddings (lo que envía OllamaLLMAdapter)."""

    model: str = ""
    prompt: str


@app.get("/health")
async def health() -> dict[str, bool]:
    """200 solo con el modelo cargado — gobierna el healthcheck del contenedor."""
    if not _state.ready:
        raise HTTPException(status_code=503, detail="model loading")
    return {"ready": True}


@app.post("/api/embeddings")
async def embeddings(req: EmbeddingsRequest) -> dict[str, list[float]]:
    """Emula Ollama: un texto por request, retorna {"embedding": [...]}.

    El texto llega CON prefijo del cliente E5. Se enruta al mismo método
    fastembed que usaba el path directo para preservar paridad de vectores.
    """
    if not _state.ready or _state.adapter is None:
        raise HTTPException(status_code=503, detail="model loading")
    if not req.prompt:
        raise HTTPException(status_code=400, detail="empty prompt")

    adapter = _state.adapter
    try:
        async with _infer_sem:
            if req.prompt.startswith(_QUERY_PREFIX):
                # embed_query con prefijo vacío → model.query_embed(texto recibido)
                vector: list[float] = await asyncio.to_thread(
                    adapter.embed_query, req.prompt  # type: ignore[attr-defined]
                )
            else:
                # embed_passages con prefijo vacío → model.embed(texto recibido)
                response = await asyncio.to_thread(
                    adapter.embed_passages, [req.prompt]  # type: ignore[attr-defined]
                )
                vector = response.embeddings[0]
    except Exception as exc:
        # El cliente OllamaLLMAdapter muestra response.text en su IntegrationError
        # — un detail explícito vale más que el 500 genérico sin cuerpo.
        logger.exception("embeddings_sidecar_inference_failed")
        raise HTTPException(status_code=500, detail=f"inference failed: {exc}") from exc

    return {"embedding": vector}
