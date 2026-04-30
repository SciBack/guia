"""FastAPI application factory para GUIA Node."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from guia import __version__
from guia.api.routes import admin, chat, harvest, health, oai, profile
from guia.config import GUIASettings
from guia.container import GUIAContainer
from guia.logging import configure_logging, get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Lifespan: construye el container al inicio y libera recursos al cierre."""
    settings: GUIASettings = app.state.settings
    configure_logging(
        level=settings.log_level,
        json_logs=(settings.environment != "development"),
    )

    logger.info("guia_starting", version=__version__, mode=str(settings.guia_llm_mode))

    container = GUIAContainer(settings)
    app.state.container = container

    logger.info("guia_ready")
    yield

    logger.info("guia_shutting_down")
    container.close()


def create_app(settings: GUIASettings | None = None) -> FastAPI:
    """Crea y configura la aplicación FastAPI.

    Args:
        settings: Configuración explícita. Si es None, lee del entorno.

    Returns:
        Aplicación FastAPI lista para servir.
    """
    _settings = settings or GUIASettings()

    app = FastAPI(
        title="GUIA Node API",
        description="Gateway Universitario de Información y Asistencia — API REST",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if _settings.environment != "production" else None,
        redoc_url="/redoc" if _settings.environment != "production" else None,
    )

    # Guardar settings en state para acceso desde endpoints
    app.state.settings = _settings

    # CORS — en producción restringir a dominios universitarios
    app.add_middleware(
        CORSMiddleware,
        allow_origins=(
            ["*"] if _settings.environment == "development" else [_settings.guia_base_url]
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Registrar routers
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(harvest.router)
    # M3: nuevos routers (ADR-029 / ADR-031 / ADR-034)
    app.include_router(oai.router)
    app.include_router(profile.router)
    # P1.3: audit admin (ADR-036)
    app.include_router(admin.router)

    return app
