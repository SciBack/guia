"""POST /api/admin/harvest — trigger manual de cosecha."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from guia.api.deps import get_harvester_service
from guia.api.schemas import HarvestRequestSchema, HarvestResponseSchema
from guia.services.harvester import HarvesterService

router = APIRouter(prefix="/api/admin", tags=["admin"])

_ADMIN_TOKEN_HEADER = "X-Admin-Token"


def _verify_admin(x_admin_token: str | None = Header(None, alias=_ADMIN_TOKEN_HEADER)) -> None:
    """Verifica token de admin en header. Placeholder hasta Sprint 0.6."""
    expected = os.environ.get("GUIA_ADMIN_TOKEN", "")
    if not expected:
        return
    if x_admin_token != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token de administrador inválido",
        )


@router.post(
    "/harvest",
    response_model=HarvestResponseSchema,
    dependencies=[Depends(_verify_admin)],
)
def trigger_harvest(
    body: HarvestRequestSchema,
    harvester: Annotated[HarvesterService, Depends(get_harvester_service)],
) -> HarvestResponseSchema:
    """Dispara una cosecha de publicaciones desde las fuentes configuradas."""
    results: dict[str, dict[str, int]] = {}

    if body.source in ("dspace", "all"):
        results["dspace"] = harvester.harvest_dspace(from_date=body.from_date)

    if body.source in ("ojs", "all"):
        results["ojs"] = harvester.harvest_ojs()

    if body.source in ("alicia", "all"):
        results["alicia"] = harvester.harvest_alicia(from_date=body.from_date)

    return HarvestResponseSchema(results=results)
