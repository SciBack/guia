"""El orden de registro decide quien atiende /ready.

Comprobado en produccion el 09-sep-2026: con ``chainlit run``, una ruta
anadida al ``app`` de ``chainlit.server`` quedaba DETRAS del catch-all
``/{full_path:path}`` que Chainlit registra al importarse, y la peticion la
atendia la SPA — 200 con HTML. El healthcheck del contenedor daba "healthy"
con los modelos a medio cargar: justo lo que la sonda existe para impedir.

La forma documentada (``mount_chainlit`` dentro de un FastAPI propio) invierte
el orden: nuestras rutas se registran antes del montaje y ganan. Estas pruebas
fijan las dos mitades — que registrar despues no vale, y que registrar antes
si.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient


@pytest.fixture
def app_con_catchall() -> FastAPI:
    """Reproduce la forma del server de Chainlit: un catch-all ya registrado."""
    app = FastAPI()

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> HTMLResponse:
        return HTMLResponse("<html><div id='root'></div></html>")

    return app


class TestSondaDeReadiness:
    def test_una_ruta_registrada_despues_la_traga_el_catchall(
        self, app_con_catchall: FastAPI
    ) -> None:
        """El fallo original, fijado para que no vuelva a colarse."""

        @app_con_catchall.get("/ready")
        async def ready() -> dict[str, bool]:
            return {"ready": True}

        r = TestClient(app_con_catchall).get("/ready")

        assert r.status_code == 200
        assert "<html>" in r.text, "si esto falla, FastAPI cambio el orden de match"


class TestOrdenDeRegistro:
    """La mitad que arregla el fallo: registrar ANTES del catch-all."""

    def test_una_ruta_registrada_antes_si_gana(self) -> None:
        """Es lo que consigue mount_chainlit al montar sobre nuestro FastAPI."""
        app = FastAPI()

        @app.get("/ready")
        async def ready() -> dict[str, bool]:
            return {"ready": True}

        @app.get("/{full_path:path}")
        async def spa(full_path: str) -> HTMLResponse:
            return HTMLResponse("<html><div id='root'></div></html>")

        cliente = TestClient(app)

        assert json.loads(cliente.get("/ready").text) == {"ready": True}
        assert "<html>" in cliente.get("/cualquier/otra").text


class TestRespuestaDeLaSonda:
    """api y web tienen que contestar lo mismo: una sola fuente de verdad."""

    def test_503_mientras_cargan_los_modelos(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from guia.services import warmup

        monkeypatch.setattr(warmup, "ESTADO", warmup._EstadoDeWarmup())

        codigo, cuerpo = warmup.respuesta_de_readiness()

        assert codigo == 503
        assert cuerpo["ready"] is False
        assert "cargando" in str(cuerpo["reason"])

    def test_200_cuando_ya_estan_dentro(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from guia.services import warmup

        estado = warmup._EstadoDeWarmup()
        estado.marcar_listo()
        monkeypatch.setattr(warmup, "ESTADO", estado)

        assert warmup.respuesta_de_readiness() == (200, {"ready": True})
