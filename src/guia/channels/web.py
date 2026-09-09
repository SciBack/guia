"""Punto de entrada del canal web: FastAPI propio con Chainlit montado dentro.

Esta es la forma que documenta Chainlit para convivir con rutas propias
(``docs.chainlit.io/integrations/fastapi``): la aplicacion FastAPI es nuestra,
nuestras rutas se registran primero, y Chainlit se monta con
``mount_chainlit``.

Antes se arrancaba con ``chainlit run`` y se le colgaban rutas al ``app`` que
``chainlit.server`` expone. Eso no funciona y no fallaba de forma visible:
Chainlit registra al importarse un catch-all ``/{full_path:path}`` que sirve la
SPA, FastAPI casa por orden, y toda ruta anadida despues quedaba detras. La
sonda ``/ready`` devolvia el HTML de la SPA con 200 y el healthcheck daba
"healthy" con los modelos a medio cargar — lo contrario de lo que la sonda
existe para conseguir. Comprobado en produccion el 09-sep-2026.

Se monta en la raiz, no en ``/chainlit``, para no mover ninguna URL: las de
callback de Keycloak, el dominio y el nginx siguen igual. Chainlit contempla
ese caso explicitamente — ``_get_auth_response`` hace
``root_path = "" if root_path == "/" else root_path`` y ``get_html_template``
hace ``rstrip("/")``—, asi que el redirect de OAuth y las rutas de los assets
quedan identicas a las de ``chainlit run``.
"""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from chainlit.utils import mount_chainlit
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from guia.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from starlette.types import ASGIApp, Receive, Scope, Send

logger = get_logger(__name__)

#: El modulo con los decoradores de Chainlit, relativo al directorio de trabajo
#: del contenedor (/app). ``mount_chainlit`` lo carga con ``load_module``.
_APP_CHAINLIT = "src/guia/channels/chainlit_app.py"


class _SinCacheEnAjustes:
    """``/project/settings`` no puede quedar cacheado.

    Es una ruta de Chainlit, asi que no se puede redefinir: se intercepta antes
    de enrutar. ASGI puro y no ``BaseHTTPMiddleware`` para no interferir con el
    WebSocket ni con el long-polling de Socket.io.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != "/project/settings":
            await self.app(scope, receive, send)
            return

        async def _enviar_sin_cache(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append(
                    (b"cache-control", b"no-store, no-cache, must-revalidate")
                )
                headers.append((b"pragma", b"no-cache"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, _enviar_sin_cache)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Precalienta los modelos al arrancar el canal web.

    Tiene que estar AQUI y no en ``@cl.on_app_startup``: Starlette no propaga
    los eventos de ciclo de vida a las sub-aplicaciones montadas, asi que el
    lifespan de Chainlit —donde vive ese hook— no llega a ejecutarse cuando se
    monta con ``mount_chainlit``. Comprobado antes de migrar; de no haberlo
    visto, el warmup habria dejado de correr en silencio y /ready no se habria
    puesto en verde nunca.

    Se usa el mismo ``warmup_models`` que la API, en vez de una copia paralela:
    antes habia dos listas de componentes que precalentar y se desincronizaron
    (a la del canal web le faltaban spaCy y SymSpell).

    En segundo plano, para que el proceso acepte conexiones de inmediato. Quien
    decide si ya se puede atender es /ready, no esto.
    """
    from guia.channels import chainlit_app
    from guia.services.warmup import warmup_models

    tarea = asyncio.create_task(warmup_models(chainlit_app._container))
    logger.info("canal_web_listo_warmup_en_curso")
    yield

    tarea.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await tarea


app = FastAPI(title="GUIA — canal web", lifespan=lifespan)


@app.get("/ready", include_in_schema=False)
async def ready() -> JSONResponse:
    """Sonda de readiness: 200 solo cuando los modelos pesados estan cargados.

    Distinta del ``/healthz`` de Chainlit, que contesta en cuanto el proceso
    levanta: eso es correcto para liveness, pero enganoso para enrutar trafico,
    porque los modelos tardan ~33 s mas y una consulta que cae en esa ventana
    se quedaba esperando detras de sus cargas.

    Se registra ANTES del ``mount_chainlit`` de abajo, que es justamente lo que
    le da precedencia sobre el catch-all de la SPA.
    """
    from guia.services.warmup import respuesta_de_readiness

    codigo, cuerpo = respuesta_de_readiness()
    return JSONResponse(cuerpo, status_code=codigo)


app.add_middleware(_SinCacheEnAjustes)

# Ultimo: al montar en "/" atrapa todo lo que no haya casado arriba.
mount_chainlit(app=app, target=str(Path(_APP_CHAINLIT)), path="/")
