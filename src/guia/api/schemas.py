"""Schemas Pydantic v2 para la API REST de GUIA."""

from __future__ import annotations

from pydantic import BaseModel, Field

from guia.domain.chat import Intent, Source


class ChatRequestSchema(BaseModel):
    """Request body para POST /api/chat."""

    query: str = Field(..., min_length=1, max_length=2000, description="Consulta del usuario")
    session_id: str | None = Field(None, description="ID de sesión para contexto")
    language: str = Field("es", description="Código de idioma (ISO 639-1)")


class ChatResponseSchema(BaseModel):
    """Response de POST /api/chat."""

    answer: str
    intent: Intent
    sources: list[Source]
    model_used: str
    cached: bool
    tokens_used: int


class HarvestRequestSchema(BaseModel):
    """Request body para POST /api/admin/harvest."""

    source: str = Field(
        "all",
        description="Fuente a cosechar: dspace | ojs | alicia | all",
        pattern="^(dspace|ojs|alicia|all)$",
    )
    from_date: str | None = Field(
        None,
        description="Fecha inicio cosecha incremental (ISO 8601, ej: 2024-01-01)",
    )


class HarvestResponseSchema(BaseModel):
    """Response de POST /api/admin/harvest."""

    results: dict[str, dict[str, int]]
    message: str = "Harvest completed"


class HealthResponseSchema(BaseModel):
    """Response de GET /health."""

    status: str = "ok"
    version: str
    environment: str
    services: dict[str, str]
