"""GET /health — health check de GUIA."""

from __future__ import annotations

from fastapi import APIRouter, Request

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
