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

    logger.info("warmup_complete")
