"""POST /api/chat — endpoint principal del asistente GUIA."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from guia.api.deps import get_chat_service
from guia.api.schemas import ChatRequestSchema, ChatResponseSchema
from guia.domain.chat import ChatRequest
from guia.services.chat import ChatService

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponseSchema)
def chat(
    body: ChatRequestSchema,
    chat_svc: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatResponseSchema:
    """Envía una consulta al asistente GUIA y recibe una respuesta con fuentes."""
    request = ChatRequest(
        query=body.query,
        session_id=body.session_id,
        language=body.language,
    )
    response = chat_svc.answer(request)

    return ChatResponseSchema(
        answer=response.answer,
        intent=response.intent,
        sources=response.sources,
        model_used=response.model_used,
        cached=response.cached,
        tokens_used=response.tokens_used,
    )
