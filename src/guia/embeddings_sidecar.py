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

Además del embedder, este proceso sirve el **reranker** (cross-encoder) por
``POST /api/rerank``. Vive aquí por la misma razón: una sola copia del modelo
en RAM para todos los canales. Se carga perezosamente en la primera petición,
así que un despliegue con ``RERANK_ENABLED=false`` no paga su memoria.

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
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, ClassVar

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from guia.logging import configure_logging, get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = get_logger(__name__)

_QUERY_PREFIX = "query: "

# Reranker por defecto: mMARCO mMiniLMv2 (Apache-2.0, ONNX oficial en HF).
# Se eligió sobre jina-reranker-v2-multilingual —mejor en benchmarks— porque
# aquel es cc-by-nc-4.0 y este producto se licencia a instituciones; y sobre
# bge-reranker-base (MIT) porque el fine-tuning de aquel es zh/en, mientras
# mMARCO incluye español entre sus 14 idiomas.
_DEFAULT_RERANK_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
_RERANK_MODEL = os.getenv("RERANK_MODEL", _DEFAULT_RERANK_MODEL)
_RERANK_ONNX_FILE = os.getenv("RERANK_ONNX_FILE", "onnx/model.onnx")


# ── Dos colas: interactiva y por lotes ─────────────────────────────────────
#
# El problema que resuelve, medido el 09-sep-2026: con una sola cola FIFO, una
# consulta de usuario esperaba detrás de todo lo que la cosecha hubiera
# encolado. Una búsqueda que en reposo tarda 0,8 s tardó 11,4 s mientras se
# recosechaban 10.000 documentos.
#
# La idea es simple: los lotes ceden el paso. Antes de pedir turno comprueban
# que no haya nadie interactivo esperando, y si lo hay, aguardan.
#
# Lo que esto NO puede hacer, y conviene tenerlo claro: interrumpir una
# inferencia ya en marcha. ONNX no se puede desalojar a media pasada. Así que
# el peor caso de una consulta interactiva pasa de "toda la cola de la cosecha"
# a "un forward de lote", que son ~50 ms porque el harvester embebe de uno en
# uno. Es la diferencia entre esperar segundos y esperar una milésima parte.
#
# Alternativa descartada: dos instancias del sidecar en máquinas distintas, que
# es lo que recomienda ONNX Runtime. No cabe — la red de UPeU solo deja pasar
# los puertos 8000 y 9200 entre el .167 y el .210, así que la imagen no se
# puede llevar al otro servidor. Cuando se abra un puerto, esa sigue siendo la
# solución mejor.
class ColaDeInferencia:
    """Reparte el turno de inferencia dando preferencia a lo interactivo.

    Es una clase y no un puñado de variables de módulo por una razón práctica:
    los primitivos de asyncio se atan al bucle de eventos donde se usan por
    primera vez. Como variables globales creadas al importar, quedaban atados
    al primer bucle y cualquier prueba con su propio bucle reventaba con
    "bound to a different event loop". En producción no se notaba —hay un solo
    bucle— pero volvía el reparto de turnos imposible de probar, que es
    justamente lo que más falta hace comprobar aquí.

    Lo que NO hace, y conviene tenerlo claro: interrumpir una inferencia en
    marcha. ONNX no se desaloja a media pasada. Lo que se consigue es que los
    lotes no se encolen por delante, así que el peor caso de una consulta pasa
    de "toda la cola de la cosecha" a "un forward de lote" — unos 50 ms, porque
    el harvester embebe de uno en uno.
    """

    def __init__(self) -> None:
        # Una inferencia a la vez: la sesión ONNX y los buffers de fastembed se
        # comparten, y dos forwards simultáneos duplicarían el pico de RAM.
        self._turno = asyncio.Semaphore(1)
        # Antesala de los lotes: solo uno compite por el turno a la vez. Sin
        # esto, ceder el paso no servía de nada — los lotes comprobaban que no
        # había nadie interactivo UNA vez y luego se encolaban todos en el
        # semáforo, así que una consulta que llegara después quedaba la última.
        # Lo destapó una prueba: el usuario acababa en la posición 6 de 6.
        self._antesala_lotes = asyncio.Semaphore(1)
        self._interactivas_en_espera = 0
        self._sin_interactivas = asyncio.Event()
        self._sin_interactivas.set()

    @asynccontextmanager
    async def turno(self, prioritaria: bool = True) -> AsyncGenerator[None]:
        """Pide turno. Los lotes (``prioritaria=False``) ceden el paso."""
        if not prioritaria:
            async with self._antesala_lotes:
                # Ya en la antesala, esperar a que no quede nadie interactivo.
                # Se comprueba AQUÍ, justo antes de tomar el turno, no antes de
                # hacer cola: es lo que garantiza que como mucho haya un lote
                # por delante de una consulta.
                while self._interactivas_en_espera > 0:
                    await self._sin_interactivas.wait()
                async with self._turno:
                    yield
            return

        self._interactivas_en_espera += 1
        self._sin_interactivas.clear()
        try:
            async with self._turno:
                yield
        finally:
            self._interactivas_en_espera -= 1
            if self._interactivas_en_espera == 0:
                self._sin_interactivas.set()


#: La cola del proceso. Ver la nota de arriba sobre por qué es un objeto.
COLA = ColaDeInferencia()


class _State:
    """Estado del proceso: el adapter se carga en el lifespan."""

    adapter: object | None = None
    ready: bool = False
    reranker: object | None = None
    """Cross-encoder — cargado perezosamente en la primera petición de rerank."""
    nlp: ClassVar[dict[str, object]] = {}
    """Modelos NLP compartidos. Ver la nota de ``/api/nlp``."""


_state = _State()

# Carga del reranker: serializa a los concurrentes para no bajar dos veces el
# modelo ni tener dos copias en RAM durante el arranque.
_rerank_load_lock = asyncio.Lock()

# Los modelos NLP tienen su propio cerrojo de carga y su propio semáforo de
# inferencia: son mucho más baratos que el embedder y no deben quedarse en cola
# detrás de él. Un gate de toxicidad esperando a que termine una cosecha de
# 10.000 documentos convertiría cada consulta en una espera de minutos.
_nlp_load_lock = asyncio.Lock()
_nlp_sem = asyncio.Semaphore(2)


def _build_adapter() -> object:
    """FastEmbedAdapter con prefijos vacíos — el cliente ya los antepone."""
    from sciback_embeddings_fastembed import FastEmbedAdapter, FastEmbedConfig

    return FastEmbedAdapter(
        FastEmbedConfig(_env_file=None, query_prefix="", passage_prefix="")
    )


def _build_reranker() -> object:
    """TextCrossEncoder de fastembed, registrando el modelo si no es built-in.

    fastembed trae un registro cerrado de cross-encoders; el nuestro no está en
    él, así que se declara con ``add_custom_model`` apuntando al ONNX oficial
    del repo de HuggingFace. Si algún día entra al registro, el ``try`` de abajo
    lo toma directamente y esta rama deja de ejecutarse sin tocar código.
    """
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    supported = {m["model"] for m in TextCrossEncoder.list_supported_models()}
    if _RERANK_MODEL not in supported:
        from fastembed.common.model_description import ModelSource

        TextCrossEncoder.add_custom_model(
            model=_RERANK_MODEL,
            sources=ModelSource(hf=_RERANK_MODEL),
            model_file=_RERANK_ONNX_FILE,
            description="Cross-encoder multilingüe (mMARCO) para reranking",
            license="apache-2.0",
        )
    return TextCrossEncoder(model_name=_RERANK_MODEL)


async def _get_reranker() -> object:
    """Devuelve el cross-encoder, cargándolo la primera vez."""
    if _state.reranker is not None:
        return _state.reranker
    async with _rerank_load_lock:
        if _state.reranker is None:
            logger.info("reranker_loading", model=_RERANK_MODEL)
            _state.reranker = await asyncio.to_thread(_build_reranker)
            logger.info("reranker_ready", model=_RERANK_MODEL)
    return _state.reranker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_logging(level="INFO", json_logs=True)
    logger.info("embeddings_sidecar_starting")
    _state.adapter = _build_adapter()
    # Cargar el modelo ONNX ya (no lazy): el healthcheck del contenedor pasa
    # recién cuando /health responde 200, y los dependientes esperan healthy.
    await asyncio.to_thread(_state.adapter.embed_query, "warmup")  # type: ignore[attr-defined]

    # El reranker tambien, por el mismo motivo: cargarlo perezosamente movia
    # sus ~2,7 s a la primera consulta real del primer usuario tras cada
    # despliegue. Solo si esta activado, para no pagar su RAM cuando no se usa.
    if os.getenv("RERANK_ENABLED", "").strip().lower() in {"1", "true", "yes"}:
        try:
            await _get_reranker()
        except Exception:
            # Un reranker que no carga degrada el ranking, no tumba el servicio:
            # rerank.py conserva el orden de la fusion cuando el sidecar falla.
            logger.warning("reranker_warmup_failed", exc_info=True)

    _state.ready = True
    logger.info("embeddings_sidecar_ready")
    yield
    logger.info("embeddings_sidecar_shutting_down")


app = FastAPI(title="GUIA Embeddings Sidecar", lifespan=lifespan)


class EmbeddingsRequest(BaseModel):
    """Forma del request de Ollama /api/embeddings (lo que envía OllamaLLMAdapter)."""

    model: str = ""
    prompt: str


class RerankRequest(BaseModel):
    """Petición de reranking — forma cercana a la API de Cohere/Jina rerank."""

    query: str
    documents: list[str]
    top_n: int | None = None
    """Cuántos devolver. None = todos, reordenados."""


@app.get("/health")
async def health() -> dict[str, bool]:
    """200 solo con el modelo cargado — gobierna el healthcheck del contenedor."""
    if not _state.ready:
        raise HTTPException(status_code=503, detail="model loading")
    return {"ready": True}


@app.post("/api/embeddings")
@app.post("/lote/api/embeddings")
async def embeddings(req: EmbeddingsRequest, request: Request) -> dict[str, list[float]]:
    """Emula Ollama: un texto por request, retorna {"embedding": [...]}.

    El texto llega CON prefijo del cliente E5. Se enruta al mismo método
    fastembed que usaba el path directo para preservar paridad de vectores.
    """
    if not _state.ready or _state.adapter is None:
        raise HTTPException(status_code=503, detail="model loading")
    if not req.prompt:
        raise HTTPException(status_code=400, detail="empty prompt")

    adapter = _state.adapter
    # La ruta decide la cola: /lote/... es trabajo por lotes y cede el paso.
    # Se distingue por URL y no por un campo del cuerpo porque el cliente es
    # OllamaLLMAdapter, en sciback-core, y así no hay que tocarlo: basta con
    # apuntar el harvester a una base_url distinta.
    prioritaria = not request.url.path.startswith("/lote/")
    try:
        async with COLA.turno(prioritaria):
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


class NLPRequest(BaseModel):
    """Petición al analizador NLP compartido."""

    op: str
    """``toxicity`` | ``entities`` | ``spellcheck`` | ``language``."""
    text: str


async def _modelo_nlp(nombre: str) -> object | None:
    """Devuelve un modelo NLP, cargándolo la primera vez.

    Igual que el reranker: una sola copia en este proceso, servida a todos los
    canales. Antes cada canal cargaba la suya — medido el 09-sep-2026, eran
    1.061 MB por canal (Detoxify 712, spaCy 317, SymSpell 31) duplicados en
    api y chainlit, sobre una VM de 9,7 GB con 500 MB libres.

    Un modelo que no carga devuelve ``None`` para siempre: los llamantes tienen
    degradación segura y no tiene sentido reintentar una carga de 15 s en cada
    consulta. El fallo se registra, que es lo que faltó cuando Detoxify llevaba
    meses sin cargarse sin que nadie se enterara.
    """
    if nombre in _state.nlp:
        return _state.nlp[nombre]

    async with _nlp_load_lock:
        if nombre in _state.nlp:
            return _state.nlp[nombre]

        def _cargar() -> object | None:
            if nombre == "toxicity":
                from detoxify import Detoxify

                return Detoxify("multilingual")
            if nombre == "entities":
                import spacy

                return spacy.load(os.getenv("NLP_SPACY_MODEL", "es_core_news_lg"))
            if nombre == "spellcheck":
                from guia.nlp.speller import _get_symspell

                return _get_symspell()
            if nombre == "language":
                from guia.nlp.language import _get_model

                return _get_model()
            return None

        logger.info("nlp_modelo_cargando", modelo=nombre)
        try:
            _state.nlp[nombre] = await asyncio.to_thread(_cargar)
            logger.info("nlp_modelo_listo", modelo=nombre,
                        disponible=_state.nlp[nombre] is not None)
        except Exception:
            logger.warning("nlp_modelo_fallo", modelo=nombre, exc_info=True)
            _state.nlp[nombre] = None

    return _state.nlp[nombre]


@app.post("/api/nlp")
async def nlp(req: NLPRequest) -> dict[str, object]:
    """Analizador NLP compartido: toxicidad, entidades, ortografía e idioma.

    Existe por lo mismo que ``/api/embeddings``: los modelos pesan y no tiene
    sentido una copia por canal. Un solo endpoint con ``op`` en vez de cuatro
    rutas, para que el semáforo y la carga vivan en un único sitio.

    Nunca lanza por un modelo ausente: devuelve el valor neutro y marca
    ``disponible: false``, para que el llamante pueda registrarlo en vez de
    creerse un resultado que nadie calculó.
    """
    texto = req.text or ""
    modelo = await _modelo_nlp(req.op)

    if modelo is None:
        neutro: dict[str, object] = {
            "toxicity": {"score": 0.0},
            "entities": {"entities": {}},
            "spellcheck": {"text": texto},
            "language": {"lang": "es", "confidence": 1.0},
        }.get(req.op, {})
        return {**neutro, "disponible": False}

    async with _nlp_sem:
        if req.op == "toxicity":
            r = await asyncio.to_thread(modelo.predict, texto)  # type: ignore[attr-defined]
            return {"score": float(max(r.values())), "disponible": True}

        if req.op == "entities":
            doc = await asyncio.to_thread(modelo, texto)  # type: ignore[operator]
            ents: dict[str, list[str]] = {}
            for e in doc.ents:
                ents.setdefault(e.label_, []).append(e.text)
            return {"entities": ents, "disponible": True}

        if req.op == "spellcheck":
            from guia.nlp.speller import correct_typos

            return {
                "text": await asyncio.to_thread(correct_typos, texto),
                "disponible": True,
            }

        if req.op == "language":
            from guia.nlp.language import detect_language

            lang, conf = await asyncio.to_thread(detect_language, texto)
            return {"lang": lang, "confidence": conf, "disponible": True}

    raise HTTPException(status_code=400, detail=f"op desconocida: {req.op}")


@app.post("/api/rerank")
async def rerank(req: RerankRequest) -> dict[str, object]:
    """Reordena ``documents`` por relevancia real frente a ``query``.

    A diferencia del embedding, que comprime consulta y documento por separado
    y los compara por coseno, el cross-encoder lee el par (consulta, documento)
    junto y puntúa esa relación. Es bastante más caro —una pasada por par— y por
    eso solo se aplica al top-N que ya seleccionó la búsqueda híbrida.

    Devuelve índices contra la lista recibida, no los textos: quien llama ya
    tiene los documentos y solo necesita el nuevo orden.
    """
    if not req.query:
        raise HTTPException(status_code=400, detail="empty query")
    if not req.documents:
        return {"results": [], "model": _RERANK_MODEL}

    try:
        encoder = await _get_reranker()
        async with COLA.turno(prioritaria=True):
            scores: list[float] = await asyncio.to_thread(
                lambda: list(encoder.rerank(req.query, req.documents))  # type: ignore[attr-defined]
            )
    except Exception as exc:
        logger.exception("rerank_failed")
        raise HTTPException(status_code=500, detail=f"rerank failed: {exc}") from exc

    ranked = sorted(
        ({"index": i, "score": float(s)} for i, s in enumerate(scores)),
        key=lambda r: r["score"],
        reverse=True,
    )
    if req.top_n is not None:
        ranked = ranked[: req.top_n]
    return {"results": ranked, "model": _RERANK_MODEL}
