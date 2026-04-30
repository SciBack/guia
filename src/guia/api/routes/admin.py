"""Admin endpoints — inspección audit_log y operaciones privilegiadas (ADR-036).

GET /api/admin/audit?user_id=... — lista entries del usuario solicitado.
Requiere autenticación + rol staff/admin (UserContext.is_staff).

Cumplimiento Ley 29733: el decano u oficina de transparencia puede consultar
qué queries hizo un usuario, qué proveedor LLM se usó y qué fuentes se
consultaron — sin exponer la query original (solo su hash sha256).
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from guia.api.deps import get_audit_repo
from guia.audit import AuditLogRepository
from guia.auth.identity import IdentityService, UserContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])
_bearer = HTTPBearer(auto_error=False)


async def _require_staff(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> UserContext:
    """Dependency: 401 sin token, 403 sin rol staff."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere autenticación",
            headers={"WWW-Authenticate": "Bearer"},
        )
    container = request.app.state.container
    identity_service = IdentityService(container.settings)  # type: ignore[arg-type]
    try:
        user = await identity_service.verify_token(credentials.credentials)
    except Exception as exc:
        logger.warning("admin_auth_failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        ) from exc

    if not user.is_staff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requiere rol staff/admin",
        )
    return user


@router.get("/audit", summary="Lista audit_log de un usuario (staff/admin)")
async def list_audit_entries(
    user_id: Annotated[str, Query(min_length=1, description="user_id a consultar")],
    repo: Annotated[AuditLogRepository, Depends(get_audit_repo)],
    _user: Annotated[UserContext, Depends(_require_staff)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> dict[str, Any]:
    """Devuelve las últimas N entradas de audit del usuario solicitado.

    REGLA: cada entry contiene query_hash (sha256) — NUNCA la query original.
    Para entender qué consultó el usuario, cruzar con logs aplicativos por
    correlation-id; no se reconstruye la query desde el hash.
    """
    entries = await repo.get_by_user(user_id, limit=limit)
    return {
        "user_id": user_id,
        "count": len(entries),
        "entries": [
            {**asdict(e), "created_at": e.created_at.isoformat()} for e in entries
        ],
    }
