"""Endpoint para que el usuario logueado en la web vincule su cuenta Telegram.

Sprint 0.5 fase 2 (ADR-040).

Flujo:
  1. Usuario manda /vincular al bot Telegram → recibe OTP de 6 dígitos.
  2. Usuario logueado en https://guia.upeu.edu.pe envía:
        POST /api/auth/telegram/link
        Authorization: Bearer <jwt_keycloak>
        Body: { "otp": "123456" }
  3. Backend verifica JWT, lee OTP de Redis, crea binding en Postgres, borra OTP.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from guia.auth.identity import IdentityService, UserContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/telegram", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


async def _get_user_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> UserContext:
    """Dependency: extrae UserContext del Bearer JWT (mismo patrón que profile)."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere autenticación con cuenta UPeU",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = request.app.state.settings
    identity_service = IdentityService(settings)
    try:
        user = await identity_service.verify_token(credentials.credentials)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    # Defensa: si KeycloakPort fallo al inicializar, verify_token devuelve
    # anonymous. NO aceptar anonymous en endpoint que requiere identidad.
    if not user.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backend de autenticación no disponible. Reintente luego.",
        )
    return user


class LinkRequest(BaseModel):
    """Body del POST /api/auth/telegram/link."""

    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class LinkResponse(BaseModel):
    """Respuesta tras vinculación exitosa."""

    status: str
    telegram_user_id: int
    telegram_username: str | None = None
    keycloak_sub: str
    keycloak_email: str | None = None


class StatusResponse(BaseModel):
    """Respuesta de GET /status."""

    linked: bool
    telegram_user_id: int | None = None
    telegram_username: str | None = None
    created_at: str | None = None


@router.post("/link", response_model=LinkResponse)
async def link_telegram(
    body: LinkRequest,
    user: Annotated[UserContext, Depends(_get_user_context)],
    request: Request,
) -> LinkResponse:
    """Asocia un OTP generado por el bot con la identidad Keycloak del caller."""
    container = request.app.state.container
    service = getattr(container, "telegram_link_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de vinculación no disponible",
        )

    binding = await service.consume_otp(
        code=body.otp,
        keycloak_sub=user.user_id,
        keycloak_email=user.email,
        keycloak_username=user.display_name or None,
    )
    if binding is None:
        logger.info(
            "telegram_link_otp_invalid",
            extra={"keycloak_sub": user.user_id, "otp_prefix": body.otp[:2]},
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Código inválido o expirado. Pide uno nuevo con /vincular en Telegram.",
        )

    logger.info(
        "telegram_link_success",
        extra={
            "keycloak_sub": user.user_id,
            "telegram_user_id": binding.telegram_user_id,
        },
    )
    return LinkResponse(
        status="linked",
        telegram_user_id=binding.telegram_user_id,
        telegram_username=binding.telegram_username,
        keycloak_sub=binding.keycloak_sub,
        keycloak_email=binding.keycloak_email,
    )


@router.get("/status", response_model=StatusResponse)
async def link_status(
    user: Annotated[UserContext, Depends(_get_user_context)],
    request: Request,
) -> StatusResponse:
    """Devuelve si el usuario tiene una cuenta Telegram vinculada."""
    container = request.app.state.container
    service = getattr(container, "telegram_link_service", None)
    if service is None:
        return StatusResponse(linked=False)
    repo = container.telegram_link_repository
    # Busca por keycloak_sub (lookup secundario; usamos query directo en repo)
    if repo._conn is None:  # noqa: SLF001 — best-effort, sin método público
        return StatusResponse(linked=False)
    row = repo._conn.execute(  # type: ignore[union-attr] # noqa: SLF001
        "SELECT telegram_user_id, telegram_username, created_at "
        "FROM guia_telegram_bindings WHERE keycloak_sub = %s",
        (user.user_id,),
    ).fetchone()
    if row is None:
        return StatusResponse(linked=False)
    return StatusResponse(
        linked=True,
        telegram_user_id=row[0],
        telegram_username=row[1],
        created_at=row[2].isoformat() if row[2] else None,
    )


@router.delete("/link")
async def unlink_telegram(
    user: Annotated[UserContext, Depends(_get_user_context)],
    request: Request,
) -> dict:
    """Desvincula la cuenta Telegram del usuario actual (lado web)."""
    container = request.app.state.container
    service = getattr(container, "telegram_link_service", None)
    repo = getattr(container, "telegram_link_repository", None)
    if service is None or repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de vinculación no disponible",
        )
    # Buscar telegram_user_id por keycloak_sub
    if repo._conn is None:  # noqa: SLF001
        return {"status": "not_linked"}
    row = repo._conn.execute(  # type: ignore[union-attr] # noqa: SLF001
        "SELECT telegram_user_id FROM guia_telegram_bindings WHERE keycloak_sub = %s",
        (user.user_id,),
    ).fetchone()
    if row is None:
        return {"status": "not_linked"}
    deleted = await service.unlink(int(row[0]))
    return {"status": "unlinked" if deleted else "not_linked"}
