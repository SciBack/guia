"""Dependency injection para FastAPI."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from guia.container import GUIAContainer
from guia.services.chat import ChatService
from guia.services.harvester import HarvesterService
from guia.services.search import SearchService


def get_container(request: Request) -> GUIAContainer:
    """Retorna el GUIAContainer almacenado en el estado de la app."""
    return request.app.state.container  # type: ignore[no-any-return]


def get_chat_service(
    container: Annotated[GUIAContainer, Depends(get_container)],
) -> ChatService:
    """Inyecta el ChatService."""
    return container.chat_service  # type: ignore[return-value]


def get_harvester_service(
    container: Annotated[GUIAContainer, Depends(get_container)],
) -> HarvesterService:
    """Inyecta el HarvesterService."""
    return container.harvester_service  # type: ignore[return-value]


def get_search_service(
    container: Annotated[GUIAContainer, Depends(get_container)],
) -> SearchService:
    """Inyecta el SearchService."""
    return container.search_service  # type: ignore[return-value]
