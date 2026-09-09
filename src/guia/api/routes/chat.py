"""POST /api/chat — endpoint principal del asistente GUIA."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from guia.api.deps import get_chat_service
from guia.api.schemas import ChatRequestSchema, ChatResponseSchema
from guia.domain.chat import ChatRequest
from guia.services.chat import ChatService

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponseSchema)
async def chat(
    body: ChatRequestSchema,
    chat_svc: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatResponseSchema:
    """Envía una consulta al asistente GUIA y recibe una respuesta con fuentes."""
    _exigir_modelos_cargados()
    request = ChatRequest(
        query=body.query,
        session_id=body.session_id,
        language=body.language,
        user_id=body.user_id,
    )
    response = await chat_svc.answer(request)

    return ChatResponseSchema(
        answer=response.answer,
        intent=response.intent,
        sources=response.sources,
        model_used=response.model_used,
        cached=response.cached,
        tokens_used=response.tokens_used,
    )


def _exigir_modelos_cargados() -> None:
    """Rechaza rapido mientras el proceso todavia esta cargando modelos.

    Entre el arranque y el fin del warmup (~60 s tras cada despliegue) los
    modelos NLP se estan cargando. Una consulta que caia ahi no fallaba: se
    quedaba esperando detras de esas cargas y tardaba mas de un minuto en
    contestar — medido en 78 s el 09-sep-2026.

    Un 503 inmediato con ``Retry-After`` es mejor trato que ese minuto de
    espera: el cliente sabe que pasa y cuando volver. El healthcheck mira
    ``/ready``, asi que un despliegue ordenado no llega ni a exponer esto.
    """
    from guia.services.warmup import ESTADO

    if ESTADO.done:
        return
    raise HTTPException(
        status_code=503,
        detail=(
            "GUIA está terminando de arrancar (cargando los modelos). "
            "Vuelve a intentarlo en unos segundos."
        ),
        headers={"Retry-After": "20"},
    )
