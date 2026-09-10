"""Modelos de dominio para el chat de GUIA.

Estos modelos son propios de GUIA y NO pertenecen a sciback-core.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

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
    source_type: str | None = None  # publication | thesis | article | koha | None si no se conoce


class SourceBucket(BaseModel):
    """Agrupación de hits por fuente consultada en el ecosistema institucional.

    Permite al usuario ver de qué portal vinieron los resultados y abrir la
    búsqueda completa en ese portal con un click (discovery layer).
    """

    model_config = ConfigDict(frozen=True)

    source_type: str  # koha | ojs | dspace | alicia
    label: str  # "Biblioteca UPeU (catálogo Koha)"
    url: str  # link al portal con query pre-cargada
    count: int  # hits efectivamente devueltos en esta respuesta


class ExploreLink(BaseModel):
    """Sugerencia de explorar el mismo tema en una fuente externa NO indexada en GUIA.

    Se usa para abrir el horizonte del usuario hacia repositorios institucionales
    o agregadores que no están dentro del index local (p.ej. DSpace bloqueado, ALICIA).
    """

    model_config = ConfigDict(frozen=True)

    source_type: str  # dspace | alicia | ...
    label: str  # "ALICIA — producción científica nacional"
    url: str  # búsqueda en la fuente externa
    available: bool = True  # False si la fuente está pendiente de habilitar


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
    #: Correo verificado por Keycloak/M365 del que está preguntando. Lo rellena
    #: SOLO el canal que ha autenticado —hoy Chainlit, tras el ``oauth_callback``—
    #: y con él GUIA responde datos personales del titular.
    #:
    #: No se reutiliza ``user_id`` para esto a propósito. ``user_id`` llega en el
    #: cuerpo de ``POST /api/chat``, que no autentica a nadie: sirve para el
    #: bucketing A/B y da igual que lo elija quien llama. Colgarle datos
    #: personales lo convertiría en una credencial falsificable —bastaría poner
    #: el correo de otra persona— así que la identidad viaja aparte y
    #: ``ChatRequestSchema`` no la expone.
    identidad_verificada: str | None = None
    #: Nombre para mostrar, de la misma sesión autenticada. Solo estética.
    nombre_verificado: str | None = None
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
    # Discovery layer (serendipia controlada): solo se pueblan en intents de búsqueda
    # con hits. Se omiten en GREETING / OUT_OF_SCOPE / CAMPUS.
    source_buckets: list[SourceBucket] = Field(default_factory=list)
    explore_in: list[ExploreLink] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)
    # Tipo de respuesta — gobierna el render de citas en el canal:
    # "list" → cada resultado es un enlace inline clicable (sin sección de fuentes
    #          duplicada abajo). "narrative" → prosa + fuentes consultadas al final.
    # Se deriva en ChatService (punto único para agente + legacy). Default conserva
    # el comportamiento histórico y no invalida entradas de caché serializadas.
    answer_type: Literal["list", "narrative"] = "narrative"
