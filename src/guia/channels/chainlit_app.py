"""Chainlit app — chat web de GUIA (Sprint 0.3).

Integra ChatService con la interfaz web de Chainlit.
Soporta streaming cuando el LLM lo provea.

Arranque:
    chainlit run src/guia/channels/chainlit_app.py --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import chainlit as cl

from guia.config import GUIASettings
from guia.container import GUIAContainer
from guia.domain.chat import ChatRequest
from guia.logging import configure_logging, get_logger

_settings = GUIASettings()
configure_logging(level=_settings.log_level, json_logs=False)
logger = get_logger(__name__)

_container = GUIAContainer(_settings)


@cl.oauth_callback
def oauth_callback(
    provider_id: str,
    token: str,
    raw_user_data: dict[str, object],
    default_user: cl.User,
) -> cl.User | None:
    """Valida el usuario autenticado via Keycloak → MicrosoftUPeU."""
    email = str(raw_user_data.get("email", ""))
    if not email.endswith("@upeu.edu.pe"):
        logger.warning("oauth_rejected", email=email, provider=provider_id)
        return None  # rechaza cuentas que no son UPeU

    name = str(raw_user_data.get("name", email.split("@", maxsplit=1)[0]))
    logger.info("oauth_login", email=email, name=name)
    return cl.User(identifier=email, metadata={"name": name, "provider": provider_id})


@cl.set_starters
async def set_starters() -> list[cl.Starter]:
    return [
        cl.Starter(
            label="Tesis sobre IA en educación",
            message="¿Hay tesis sobre inteligencia artificial aplicada a la educación superior?",
            icon="/public/favicon.png",
        ),
        cl.Starter(
            label="Nutrición infantil en zonas rurales",
            message="Busca artículos recientes sobre nutrición infantil en comunidades rurales",
            icon="/public/favicon.png",
        ),
        cl.Starter(
            label="Facultad de Ingeniería — energías renovables",
            message="¿Qué investigaciones hay de la Facultad de Ingeniería sobre energías renovables?",
            icon="/public/favicon.png",
        ),
        cl.Starter(
            label="Teología adventista post-2020",
            message="Muéstrame trabajos sobre teología adventista publicados después de 2020",
            icon="/public/favicon.png",
        ),
    ]


@cl.on_chat_start
async def on_chat_start() -> None:
    """Inicializa la sesión de chat."""
    user = cl.user_session.get("user")
    cl.user_session.set("session_id", cl.context.session.id)

    name = user.metadata.get("name", "usuario") if user else "usuario"
    await cl.Message(
        content=(
            f"Hola **{name}**, soy **GUIA**, tu asistente universitario UPeU. "
            "Puedo ayudarte a encontrar tesis, artículos y publicaciones "
            "del repositorio institucional. ¿En qué te ayudo?"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    """Procesa cada mensaje del usuario."""
    session_id: str = cl.user_session.get("session_id", "")

    # Indicador de "pensando"
    thinking_msg = cl.Message(content="")
    await thinking_msg.send()

    try:
        request = ChatRequest(
            query=message.content,
            session_id=session_id,
            language="es",
        )
        response = await _container.chat_service.answer(request)

        # Construir respuesta con fuentes
        answer_text = response.answer

        if response.sources:
            answer_text += "\n\n**Fuentes:**\n"
            for i, source in enumerate(response.sources, 1):
                if source.url:
                    answer_text += f"{i}. [{source.title}]({source.url})\n"
                else:
                    answer_text += f"{i}. {source.title}\n"

        if response.cached:
            answer_text += "\n\n*Respuesta desde caché semántico*"

        thinking_msg.content = answer_text
        await thinking_msg.update()

    except Exception as exc:
        logger.exception("chainlit_error", exc_info=exc)
        thinking_msg.content = (
            "Lo siento, ocurrió un error procesando tu consulta. "
            "Por favor, inténtalo de nuevo."
        )
        await thinking_msg.update()


@cl.on_chat_end
async def on_chat_end() -> None:
    """Limpieza al finalizar sesión."""
    logger.info("chainlit_session_end", session_id=cl.user_session.get("session_id", ""))
