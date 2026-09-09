"""El submontaje de Chainlit no puede romper el streaming de Socket.io.

``mount_chainlit`` anade un ChainlitMiddleware que devuelve 404 a todo lo que no
empiece por el prefijo de montaje. Montando en "/" ese filtro no descarta nada
—todo empieza por "/"— pero no es inocuo: es un ``BaseHTTPMiddleware`` y rompia
el long-polling de Socket.io. En el navegador se veia como un chat que aceptaba
el mensaje y no contestaba jamas; en los logs, esta traza (09-sep-2026):

    File ".../chainlit/utils.py", line 169, in dispatch
      return await call_next(request)
    File ".../starlette/middleware/base.py", line 171, in call_next
      assert message["type"] == "http.response.start"
    AssertionError

Aqui NO se reproduce el fallo: hace falta el anidamiento real (nuestro FastAPI →
Mount → app de Chainlit → su Socket.io) y los intentos de imitarlo con una app
ASGI cruda no lo disparan. Lo que si se fija es la tecnica de retirada, que es
lo que puede romperse al subir de version de Starlette.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware


class _Guarda(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):  # type: ignore[no-untyped-def]
        return await call_next(request)


class TestRetiradaDeLaGuarda:
    def test_quitarla_de_user_middleware_la_desactiva(self) -> None:
        """Es lo que hace _retirar_guarda_de_submontaje sobre el app de Chainlit."""
        app = FastAPI()
        marcas: list[str] = []

        @app.get("/x")
        async def x() -> dict[str, bool]:
            return {"ok": True}

        app.add_middleware(_Guarda)
        assert any(m.cls is _Guarda for m in app.user_middleware)

        app.user_middleware = [m for m in app.user_middleware if m.cls is not _Guarda]
        app.middleware_stack = None  # se reconstruye en el primer request

        assert TestClient(app).get("/x").json() == {"ok": True}
        assert not any(m.cls is _Guarda for m in app.user_middleware)
        assert marcas == []

    def test_la_pila_se_reconstruye_perezosamente(self) -> None:
        """Si Starlette dejara de construirla en __call__, la retirada no valdria
        y habria que hacerla de otro modo. Esto lo detecta al actualizar."""
        app = FastAPI()

        @app.get("/x")
        async def x() -> dict[str, bool]:
            return {"ok": True}

        assert app.middleware_stack is None, "ya no se construye perezosamente"
        TestClient(app).get("/x")
        assert app.middleware_stack is not None
