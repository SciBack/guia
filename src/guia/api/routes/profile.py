"""Profile endpoints — privacidad y control de datos de usuario (ADR-034).

Permite al usuario:
- Exportar sus datos (GDPR-compatible)
- Eliminar su perfil y historial de sesiones
- Gestionar opt-ins de personalización

M3: implementación básica sin UserProfileRepository real.
    Los datos se construyen desde la sesión Redis + Keycloak.
    M4: persistir UserProfile en Postgres.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from guia.auth.identity import IdentityService, UserContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profile", tags=["profile"])
_bearer = HTTPBearer(auto_error=False)


async def _get_user_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> UserContext:
    """Dependency: extrae y verifica UserContext del Bearer token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere autenticación",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = request.app.state.settings
    identity_service = IdentityService(settings)

    try:
        return await identity_service.verify_token(credentials.credentials)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.get("/export")
async def export_profile(
    user: Annotated[UserContext, Depends(_get_user_context)],
    request: Request,
) -> dict:
    """Exporta los datos del usuario autenticado (GDPR Art. 20 — portabilidad).

    Retorna todos los datos que GUIA tiene del usuario:
    - Identidad (id, email, rol)
    - Historial de sesión (M3: desde Redis)
    - Preferencias / opt-ins (M3: vacío — M4: desde Postgres)
    """
    logger.info("profile_export_requested", user_id=user.user_id)

    # M3: datos básicos desde el token + sesión Redis
    redis_client = getattr(request.app.state, "redis", None)
    session_data: dict = {}

    if redis_client is not None:
        try:
            session_key = f"guia:session:{user.user_id}"
            session_data = redis_client.hgetall(session_key) or {}
        except Exception as exc:
            logger.warning("profile_export_redis_error", exc=str(exc))

    return {
        "user_id": user.user_id,
        "email": user.email,
        "domain": user.domain,
        "display_name": user.display_name,
        "roles": user.roles,
        "is_staff": user.is_staff,
        "session": session_data,
        # M4: historial de queries, preferencias, opt-ins desde Postgres
        "query_history": [],
        "preferences": {},
        "opt_ins": {
            "personalization": False,  # M4: leer desde UserProfile
            "analytics": False,
        },
        "_note": "M3: datos completos disponibles en M4 con UserProfile persistido",
    }


@router.delete("")
@router.delete("/")
async def delete_profile(
    user: Annotated[UserContext, Depends(_get_user_context)],
    request: Request,
) -> dict:
    """Elimina el perfil del usuario y todas sus sesiones (derecho al olvido GDPR Art. 17).

    M3: elimina datos de Redis.
    M4: eliminar también UserProfile de Postgres.
    """
    logger.info("profile_delete_requested", user_id=user.user_id)

    deleted_keys: list[str] = []

    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is not None:
        try:
            session_key = f"guia:session:{user.user_id}"
            cache_pattern = f"guia:cache:{user.user_id}:*"

            redis_client.delete(session_key)
            deleted_keys.append(session_key)

            # Eliminar entradas de caché semántico del usuario
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor, match=cache_pattern, count=100)
                if keys:
                    redis_client.delete(*keys)
                    deleted_keys.extend(k.decode() if isinstance(k, bytes) else k for k in keys)
                if cursor == 0:
                    break

            logger.info("profile_delete_redis_ok", user_id=user.user_id, keys=len(deleted_keys))
        except Exception as exc:
            logger.error("profile_delete_redis_error", user_id=user.user_id, exc=str(exc))

    return {
        "status": "deleted",
        "user_id": user.user_id,
        "deleted_keys": len(deleted_keys),
        "_note": "M4: eliminación completa de UserProfile desde Postgres pendiente",
    }


@router.post("/opt-ins")
async def update_opt_ins(
    user: Annotated[UserContext, Depends(_get_user_context)],
    request: Request,
) -> dict:
    """Actualiza preferencias de opt-in del usuario.

    Body JSON esperado:
    {
        "personalization": true | false,
        "analytics": true | false
    }

    M3: guarda en Redis (volátil). M4: persistir en UserProfile Postgres.
    """
    body = await request.json()
    personalization = bool(body.get("personalization", False))
    analytics = bool(body.get("analytics", False))

    logger.info(
        "profile_opt_ins_updated",
        user_id=user.user_id,
        personalization=personalization,
        analytics=analytics,
    )

    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is not None:
        try:
            pref_key = f"guia:prefs:{user.user_id}"
            redis_client.hset(pref_key, mapping={
                "personalization": "1" if personalization else "0",
                "analytics": "1" if analytics else "0",
            })
            redis_client.expire(pref_key, 86400 * 30)  # 30 días
        except Exception as exc:
            logger.warning("profile_opt_ins_redis_error", exc=str(exc))

    return {
        "status": "updated",
        "opt_ins": {
            "personalization": personalization,
            "analytics": analytics,
        },
    }
