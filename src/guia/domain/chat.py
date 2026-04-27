"""Modelos de dominio para el chat de GUIA.

Estos modelos son propios de GUIA y NO pertenecen a sciback-core.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Intent(StrEnum):
    """Intenciones que GUIA puede reconocer en el mensaje del usuario.

    - RESEARCH: Búsqueda en producción científica institucional (DSpace/OJS).
    - CAMPUS: Consultas sobre servicios universitarios (Koha, SIS, ERP) — Fase 1.
    - GENERAL: Consultas generales respondibles con contexto RAG.
    - OUT_OF_SCOPE: Consulta fuera del alcance institucional.
    """

    RESEARCH = "research"
    CAMPUS = "campus"
    GENERAL = "general"
    OUT_OF_SCOPE = "out_of_scope"


class Source(BaseModel):
    """Fuente de información usada para responder al usuario."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    url: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    score: float = 0.0
    source_type: str = "publication"  # publication | thesis | article


class ConversationMessage(BaseModel):
    """Turno previo de la conversación, para contexto del LLM."""

    model_config = ConfigDict(frozen=True)

    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    """Request entrante al ChatService."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None
    session_id: str | None = None
    language: str = "es"
    intent_hint: Intent | None = None
    history: list[ConversationMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """Respuesta del ChatService al usuario."""

    model_config = ConfigDict(frozen=True)

    answer: str
    intent: Intent
    sources: list[Source] = Field(default_factory=list)
    model_used: str
    cached: bool = False
    tokens_used: int = 0
