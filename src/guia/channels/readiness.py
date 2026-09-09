"""Sonda de readiness servida como middleware ASGI.

Vive fuera de ``chainlit_app`` por dos motivos: no depende de Chainlit para
nada, y aquel construye el contenedor (y con el, la conexion a Postgres) al
importarse, lo que haria imposible probar esto sin una base de datos.

Por que middleware y no una ruta: ``chainlit.server`` registra al importarse un
catch-all ``/{full_path:path}`` que sirve la SPA, y FastAPI casa las rutas por
orden de registro. Cualquier ruta anadida despues del import queda por detras
y no se alcanza nunca. Comprobado en produccion el 09-sep-2026: ``/ready``
devolvia el HTML de la SPA con 200 y el healthcheck del contenedor daba
"healthy" sin que los modelos estuvieran cargados — justo lo contrario de lo
que la sonda existe para conseguir.

La via documentada para tener rutas propias es la contraria —montar Chainlit
dentro de tu propio FastAPI con ``mount_chainlit``, donde las tuyas se
registran primero—. Mientras GUIA arranque con ``chainlit run``, esto es lo
que no depende del orden de registro.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

RUTA = "/ready"


class ReadinessMiddleware:
    """Contesta ``/ready`` segun el estado del warmup, antes de enrutar.

    200 cuando los modelos pesados ya estan cargados; 503 mientras cargan, para
    que el healthcheck del contenedor y el balanceador no den por bueno un
    proceso que aun tardaria mas de un minuto en responder.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != RUTA:
            await self.app(scope, receive, send)
            return

        from guia.services.warmup import ESTADO

        listo = ESTADO.done
        respuesta = JSONResponse(
            {"ready": True} if listo else {"ready": False, "reason": "cargando modelos"},
            status_code=200 if listo else 503,
        )
        await respuesta(scope, receive, send)
