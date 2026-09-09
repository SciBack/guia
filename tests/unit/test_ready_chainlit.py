"""La sonda /ready del canal web tiene que ganarle al catch-all de Chainlit.

Comprobado en produccion el 09-sep-2026: registrada como ruta con
``@app.get("/ready")`` sobre ``chainlit.server.app``, la peticion la atendia el
catch-all ``/{full_path:path}`` que Chainlit registra al importarse, devolviendo
el HTML de la SPA con 200. El healthcheck del contenedor daba "healthy" sin que
los modelos estuvieran cargados: justo lo que la sonda existe para impedir.
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

    def test_el_middleware_si_la_atiende(self, app_con_catchall: FastAPI) -> None:
        from guia.channels.readiness import ReadinessMiddleware
        from guia.services import warmup

        warmup.ESTADO.marcar_listo()
        app_con_catchall.add_middleware(ReadinessMiddleware)

        r = TestClient(app_con_catchall).get("/ready")

        assert r.status_code == 200
        assert json.loads(r.text) == {"ready": True}

    def test_responde_503_mientras_cargan_los_modelos(
        self, app_con_catchall: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from guia.channels import readiness as modulo_readiness
        from guia.services.warmup import _EstadoDeWarmup

        monkeypatch.setattr("guia.services.warmup.ESTADO", _EstadoDeWarmup())
        app_con_catchall.add_middleware(modulo_readiness.ReadinessMiddleware)

        r = TestClient(app_con_catchall).get("/ready")

        assert r.status_code == 503
        assert json.loads(r.text)["ready"] is False

    def test_el_resto_de_rutas_pasa_de_largo(self, app_con_catchall: FastAPI) -> None:
        """La sonda no puede secuestrar la SPA ni el websocket."""
        from guia.channels.readiness import ReadinessMiddleware

        app_con_catchall.add_middleware(ReadinessMiddleware)

        r = TestClient(app_con_catchall).get("/cualquier/otra/cosa")

        assert "<html>" in r.text
