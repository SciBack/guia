"""GET /health — health check de GUIA."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from guia import __version__
from guia.api.schemas import HealthResponseSchema
from guia.config import GUIASettings

router = APIRouter()


@router.get("/health", response_model=HealthResponseSchema, tags=["ops"])
def health(request: Request) -> HealthResponseSchema:
    """Endpoint de salud para load balancer y Docker healthchecks."""
    settings: GUIASettings = request.app.state.settings

    services: dict[str, str] = {}

    try:
        redis_client = request.app.state.container._redis
        redis_client.ping()
        services["redis"] = "ok"
    except Exception:
        services["redis"] = "error"

    try:
        _store = request.app.state.container.store
        services["postgres"] = "ok"
    except Exception:
        services["postgres"] = "error"

    return HealthResponseSchema(
        status="ok",
        version=__version__,
        environment=settings.environment,
        services=services,
    )


@router.get("/ready", tags=["ops"])
def ready() -> JSONResponse:
    """Sonda de readiness: 200 solo cuando los modelos ya estan cargados.

    Distinta de ``/health``, que es de liveness y debe contestar pronto para
    que el orquestador no mate un proceso que solo esta arrancando. Esta es la
    que debe mirar el healthcheck del contenedor y el balanceador: entre el
    arranque y el fin del warmup el proceso acepta conexiones pero todavia no
    puede responder rapido.
    """
    from guia.services.warmup import ESTADO

    if ESTADO.done:
        return JSONResponse({"ready": True})
    return JSONResponse({"ready": False, "reason": "cargando modelos"}, status_code=503)
