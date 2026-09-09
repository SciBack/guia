"""Warmup de modelos pesados al arranque (embedder + gates NLP).

La carga lazy de fastembed e5-large (~2.5GB) en la primera query research
tras un recreate causaba OOM-kill del proceso (con swap saturado) o un 504
de nginx (carga ~60s > proxy_read_timeout) aunque el backend terminara bien.
Pre-calentar en background al arrancar elimina ese cold-start sin retrasar
el healthcheck del contenedor.

Chainlit tiene su propia versión en chainlit_app.on_app_startup (bloqueante
para routers, background para gates NLP). Este helper cubre api y telegram,
que antes no calentaban nada.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from guia.logging import get_logger

if TYPE_CHECKING:
    from guia.container import GUIAContainer

logger = get_logger(__name__)


class _EstadoDeWarmup:
    """Si los modelos pesados ya estan cargados en ESTE proceso.

    Existe porque ``/health`` respondia 200 a los 7 s de arrancar mientras el
    warmup seguia 12 s mas. En esa ventana el contenedor figuraba sano y una
    consulta que cayera dentro tardaba 65 s (medido el 09-sep-2026). Con esto
    la sonda de readiness puede decir la verdad y el orquestador esperar.
    """

    def __init__(self) -> None:
        self._done = False

    @property
    def done(self) -> bool:
        return self._done

    def marcar_listo(self) -> None:
        self._done = True


#: Estado compartido del proceso; lo consultan las sondas /ready.
ESTADO = _EstadoDeWarmup()


def respuesta_de_readiness() -> tuple[int, dict[str, object]]:
    """Codigo y cuerpo que debe devolver ``/ready``.

    Vive aqui, y no en el canal, porque api y web deben responder lo mismo y
    porque importar el canal web arrastra el contenedor entero (y con el,
    Postgres), lo que haria imposible probar esto.
    """
    if ESTADO.done:
        return 200, {"ready": True}
    return 503, {"ready": False, "reason": "cargando modelos"}



async def warmup_models(container: GUIAContainer) -> None:
    """Pre-carga embedder, routers y gates NLP. Nunca propaga errores.

    Pensado para ``asyncio.create_task`` en el startup del canal: el proceso
    sirve /health de inmediato y los modelos se cargan en paralelo. Si una
    query llega durante la carga, paga el lazy-load igual que antes — el
    warmup solo adelanta el costo, no agrega bloqueos.
    """
    # Routers — su warm_up embebe los ejemplos de centroides, lo que fuerza
    # la carga del modelo ONNX (la parte pesada, ~2.5GB / ~60s en la VM).
    for attr in ("router", "cascade_router"):
        target = getattr(container, attr, None)
        if target is None:
            continue
        try:
            logger.info("warmup_start", component=attr)
            await target.warm_up()
            logger.info("warmup_done", component=attr)
        except Exception:
            logger.warning("warmup_failed", component=attr, exc_info=True)

    # Embedder directo — red de seguridad si no hay routers configurados.
    embedder = getattr(container, "embedder", None)
    if embedder is not None:
        try:
            await asyncio.to_thread(embedder.embed_query, "warmup")
            logger.info("warmup_done", component="embedder")
        except Exception:
            logger.warning("warmup_failed", component="embedder", exc_info=True)

    # Gates NLP — lid.176.bin (idioma) y Detoxify (toxicidad). Los gates
    # tienen fallback seguro incorporado, así que un fallo aquí solo significa
    # que la primera query paga la carga.
    try:
        from guia.nlp.language import detect_language

        await asyncio.to_thread(detect_language, "warmup")
        logger.info("warmup_done", component="language_gate")
    except Exception:
        logger.warning("warmup_failed", component="language_gate", exc_info=True)

    toxicity_gate = getattr(container, "toxicity_gate", None)
    if toxicity_gate is not None:
        try:
            await asyncio.to_thread(toxicity_gate.evaluate, "warmup query")
            logger.info("warmup_done", component="toxicity_gate")
        except Exception:
            logger.warning("warmup_failed", component="toxicity_gate", exc_info=True)

    # NLP del reescritor de consultas: spaCy es_core_news_lg (~10 s) y el
    # diccionario de SymSpell (que en la primera carga puede DESCARGARSE).
    # Estaban fuera del warmup, asi que los pagaba integros la primera
    # consulta real — la mitad de los 65 s medidos el 09-sep-2026.
    for componente, cargar in (
        ("ner_spacy", _cargar_spacy),
        ("speller_symspell", _cargar_symspell),
    ):
        try:
            await asyncio.to_thread(cargar)
            logger.info("warmup_done", component=componente)
        except Exception:
            logger.warning("warmup_failed", component=componente, exc_info=True)

    ESTADO.marcar_listo()
    logger.info("warmup_complete")


def _cargar_spacy() -> None:
    from guia.nlp.ner import extract_entities

    extract_entities("warmup en la Universidad Peruana Union")


def _cargar_symspell() -> None:
    from guia.nlp.speller import correct_typos

    correct_typos("warmup")
