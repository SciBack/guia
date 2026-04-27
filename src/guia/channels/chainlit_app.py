"""Chainlit app — chat web de GUIA (Sprint 0.3).

Integra ChatService con la interfaz web de Chainlit.
Soporta streaming cuando el LLM lo provea.

Arranque:
    chainlit run src/guia/channels/chainlit_app.py --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import asyncio
import os

import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.types import ThreadDict
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from sciback_core.ports.llm import LLMMessage

from guia.config import GUIASettings
from guia.container import GUIAContainer
from guia.domain.chat import ChatRequest, ConversationMessage
from guia.logging import configure_logging, get_logger

_settings = GUIASettings()
configure_logging(level=_settings.log_level, json_logs=False)
logger = get_logger(__name__)

_container = GUIAContainer(_settings)

# URL asyncpg para el Data Layer nativo de Chainlit
_PG_URL = os.environ.get(
    "PGVECTOR_DATABASE_URL",
    "postgresql+psycopg://guia:changeme@postgres:5432/guia_db",
).replace("postgresql+psycopg://", "postgresql+asyncpg://")


@cl.data_layer
def get_data_layer() -> SQLAlchemyDataLayer:
    """Data Layer nativo de Chainlit — habilita sidebar de historial de threads."""
    return SQLAlchemyDataLayer(conninfo=_PG_URL)


@cl.on_app_startup
async def on_app_startup() -> None:
    """Pre-calienta el ModelRouter al arrancar la app."""
    router = getattr(_container, "router", None)
    if router is not None:
        logger.info("model_router_warmup_start")
        await router.warm_up()
        logger.info("model_router_warmup_done")


@cl.on_logout
def on_logout(request: Request, response: Response) -> JSONResponse:
    """Cierra la sesión de Keycloak vía admin API (sin pantalla de confirmación)
    y devuelve la URL de logout de Microsoft para que el JS encadene el cierre.
    """
    import urllib.request
    import urllib.parse

    base   = os.environ.get("OAUTH_KEYCLOAK_BASE_URL", "").rstrip("/")
    realm  = os.environ.get("OAUTH_KEYCLOAK_REALM", "upeu")
    client = os.environ.get("OAUTH_KEYCLOAK_CLIENT_ID", "guia-node")
    secret = os.environ.get("OAUTH_KEYCLOAK_CLIENT_SECRET", "")

    # 1. Obtener token de service account (client_credentials)
    try:
        token_data = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": client,
            "client_secret": secret,
        }).encode()
        req = urllib.request.Request(
            f"{base}/realms/{realm}/protocol/openid-connect/token",
            data=token_data,
        )
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310
            admin_token = __import__("json").loads(r.read())["access_token"]

        # 2. Identificar usuario desde la cookie de Chainlit (antes de que se borre)
        import jwt as pyjwt
        from chainlit.config import config as cl_config
        auth_cookie = request.cookies.get("chainlit_auth", "")
        if auth_cookie:
            payload = pyjwt.decode(
                auth_cookie,
                cl_config.auth.jwt_secret,
                algorithms=["HS256"],
                options={"verify_exp": False},
            )
            email = payload.get("identifier", "")

            if email:
                # 3. Buscar user en Keycloak
                users_url = (
                    f"{base}/admin/realms/{realm}/users"
                    f"?email={urllib.parse.quote(email)}&exact=true"
                )
                req2 = urllib.request.Request(users_url)
                req2.add_header("Authorization", f"Bearer {admin_token}")
                with urllib.request.urlopen(req2, timeout=5) as r:  # noqa: S310
                    users = __import__("json").loads(r.read())

                if users:
                    user_id = users[0]["id"]
                    # 4. Eliminar todas sus sesiones en Keycloak
                    del_req = urllib.request.Request(
                        f"{base}/admin/realms/{realm}/users/{user_id}/sessions",
                        method="DELETE",
                    )
                    del_req.add_header("Authorization", f"Bearer {admin_token}")
                    urllib.request.urlopen(del_req, timeout=5)  # noqa: S310
                    logger.info("keycloak_sessions_deleted", email=email)

    except Exception as exc:  # pragma: no cover
        logger.warning("keycloak_logout_admin_failed", error=str(exc))

    # 5. Devolver URL de logout de Microsoft para que el JS encadene
    ms_tenant = os.environ.get("AZURE_TENANT_ID", "cfbd88b4-94bc-4fba-98bd-64d0726394a3")
    app_url   = os.environ.get("CHAINLIT_URL", "").rstrip("/")
    ms_logout = (
        f"https://login.microsoftonline.com/{ms_tenant}/oauth2/v2.0/logout"
        f"?post_logout_redirect_uri={urllib.parse.quote(app_url)}"
    )
    return JSONResponse({"keycloak_logout": ms_logout})


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
    """Inicializa una sesión nueva — Chainlit gestiona la persistencia via Data Layer."""
    user = cl.user_session.get("user")
    name = user.metadata.get("name", "usuario") if user else "usuario"
    cl.user_session.set("history", [])

    await cl.Message(
        content=(
            f"Hola **{name}**, soy **GUIA**, tu asistente universitario UPeU. "
            "Puedo ayudarte a encontrar tesis, artículos y publicaciones "
            "del repositorio institucional. ¿En qué te ayudo?"
        )
    ).send()


@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict) -> None:
    """Restaura el historial cuando el usuario retoma una conversación del sidebar."""
    history: list[ConversationMessage] = []
    for step in thread.get("steps", []):
        if step.get("type") == "user_message":
            history.append(ConversationMessage(role="user", content=step.get("output", "")))
        elif step.get("type") == "assistant_message":
            history.append(ConversationMessage(role="assistant", content=step.get("output", "")))
    cl.user_session.set("history", history[-20:])
    logger.info("chat_resumed", thread_id=thread.get("id"), steps=len(history))


async def _generate_thread_title(query: str) -> str:
    """Genera un título corto (≤6 palabras) para el thread basado en la primera pregunta."""
    try:
        llm = _container.classifier_llm
        messages = [
            LLMMessage(
                role="system",
                content=(
                    "Genera un título muy corto (máximo 6 palabras) que resuma esta pregunta. "
                    "Solo el título, sin puntos, comillas ni explicaciones."
                ),
            ),
            LLMMessage(role="user", content=query),
        ]
        result = await asyncio.to_thread(llm.complete, messages, max_tokens=20, temperature=0.1)
        title = result.content.strip().strip("\"'").strip()
        return title[:60] if title else query[:60]
    except Exception:
        return query[:60]


@cl.on_message
async def on_message(message: cl.Message) -> None:
    """Procesa cada mensaje del usuario."""
    history: list[ConversationMessage] = cl.user_session.get("history", [])

    thinking_msg = cl.Message(content="")
    await thinking_msg.send()

    try:
        request = ChatRequest(
            query=message.content,
            session_id=cl.context.session.id,
            language="es",
            history=history,
        )
        response = await _container.chat_service.answer(request)

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

        # Primer turno: generar título descriptivo para el thread en el sidebar
        if not history:
            title = await _generate_thread_title(message.content)
            await cl.context.emitter.update_thread(name=title)

        # Actualizar historial en memoria de sesión (bounded a 20 mensajes = 10 turnos)
        history = history + [
            ConversationMessage(role="user", content=message.content),
            ConversationMessage(role="assistant", content=response.answer),
        ]
        cl.user_session.set("history", history[-20:])

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
    logger.info("chainlit_session_end", session_id=cl.context.session.id)
