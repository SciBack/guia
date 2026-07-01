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
from chainlit.server import app as _chainlit_app
from chainlit.types import ThreadDict
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sciback_core.ports.llm import LLMMessage
from starlette.types import ASGIApp, Receive, Scope, Send

from guia.channels.dify_client import DifyClient, DifyClientError
from guia.channels.feedback_datalayer import (
    FeedbackCapturingDataLayer,
    stash_response_metadata,
)
from guia.config import GUIASettings
from guia.container import GUIAContainer
from guia.domain.chat import ConversationMessage
from guia.logging import configure_logging, get_logger

_settings = GUIASettings()
configure_logging(level=_settings.log_level, json_logs=False)
logger = get_logger(__name__)

# _container se conserva para el data layer (Postgres), feedback (Redis) y
# generación de título de thread — YA NO se usa para responder el chat
# (FASE A migración GUIA→Dify: el "cerebro" es Dify vía el sidecar).
_container = GUIAContainer(_settings)

_dify_client = DifyClient(
    base_url=_settings.dify_sidecar_url,
    api_key=_settings.dify_sidecar_key,
    verify=_settings.dify_sidecar_verify_tls,
    timeout=_settings.dify_sidecar_timeout_s,
)


class _NoCacheSettingsMiddleware:
    """/project/settings nunca debe ser cacheado.

    ASGI puro — no usa BaseHTTPMiddleware para no interferir con
    WebSocket ni streaming (Socket.io long-polling).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != "/project/settings":
            await self.app(scope, receive, send)
            return

        async def _send_with_nocache(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"cache-control", b"no-store, no-cache, must-revalidate"))
                headers.append((b"pragma", b"no-cache"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, _send_with_nocache)


_chainlit_app.add_middleware(_NoCacheSettingsMiddleware)

# URL asyncpg para el Data Layer nativo de Chainlit
_PG_URL = os.environ.get(
    "PGVECTOR_DATABASE_URL",
    "postgresql+psycopg://guia:changeme@postgres:5432/guia_db",
).replace("postgresql+psycopg://", "postgresql+asyncpg://")


@cl.data_layer
def get_data_layer() -> SQLAlchemyDataLayer:
    """Data Layer Chainlit + captura de 👍/👎 al dataset chat_feedback.

    Si el repo de feedback no inicializó (ej. Postgres caído al arranque),
    cae al SQLAlchemyDataLayer estándar para no romper la UI.
    """
    fb_repo = getattr(_container, "feedback_repo", None)
    redis_client = getattr(_container, "redis_client", None)
    if fb_repo is not None and redis_client is not None:
        return FeedbackCapturingDataLayer(
            conninfo=_PG_URL,
            feedback_repo=fb_repo,
            redis_client=redis_client,
        )
    return SQLAlchemyDataLayer(conninfo=_PG_URL)


@cl.on_app_startup
async def on_app_startup() -> None:
    """Arranque de la app.

    FASE A migración GUIA→Dify: Dify (vía el sidecar) ahora hace el routing,
    los gates NLP y el RAG — el warmup de `router`/`cascade_router` y de los
    gates NLP locales (lid.176.bin, detoxify) ya no aplica al chat y se
    elimina. `_container` se sigue construyendo para el data layer, feedback
    y generación de título de thread.
    """
    logger.info("chainlit_startup_dify_backend")


@cl.on_logout
async def on_logout(request: Request, response: Response) -> JSONResponse:
    """Cierra la sesión de Keycloak vía admin API (sin pantalla de confirmación)
    y devuelve la URL de logout de Microsoft para que el JS encadene el cierre.
    """
    import urllib.parse

    import httpx

    base   = os.environ.get("OAUTH_KEYCLOAK_BASE_URL", "").rstrip("/")
    realm  = os.environ.get("OAUTH_KEYCLOAK_REALM", "upeu")
    client = os.environ.get("OAUTH_KEYCLOAK_CLIENT_ID", "guia-node")
    secret = os.environ.get("OAUTH_KEYCLOAK_CLIENT_SECRET", "")

    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            # 1. Obtener token de service account (client_credentials)
            r = await http.post(
                f"{base}/realms/{realm}/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": client,
                    "client_secret": secret,
                },
            )
            r.raise_for_status()
            admin_token = r.json()["access_token"]

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
                    r2 = await http.get(
                        f"{base}/admin/realms/{realm}/users",
                        params={"email": email, "exact": "true"},
                        headers={"Authorization": f"Bearer {admin_token}"},
                    )
                    r2.raise_for_status()
                    users = r2.json()

                    if users:
                        user_id = users[0]["id"]
                        # 4. Eliminar todas sus sesiones en Keycloak
                        await http.delete(
                            f"{base}/admin/realms/{realm}/users/{user_id}/sessions",
                            headers={"Authorization": f"Bearer {admin_token}"},
                        )
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


@cl.author_rename
def rename_author(orig_author: str) -> str:
    """Renombra autores de steps CoT a nombres legibles."""
    return {
        "retrieval": "Búsqueda académica",
        "embedding": "Indexación semántica",
        "rerank": "Clasificación de resultados",
        "llm": "Síntesis IA",
        "tool": "Herramienta",
    }.get(orig_author, orig_author)


@cl.set_starters
async def set_starters() -> list[cl.Starter]:
    return [
        cl.Starter(
            label="Libros sobre inteligencia artificial",
            message="¿Qué libros hay sobre inteligencia artificial en la biblioteca?",
        ),
        cl.Starter(
            label="Artículos de nutrición infantil",
            message="Busca artículos recientes sobre nutrición infantil en comunidades rurales",
        ),
        cl.Starter(
            label="Revistas de ingeniería — energías renovables",
            message="¿Qué publicaciones hay sobre energías renovables en las revistas UPeU?",
        ),
        cl.Starter(
            label="Literatura sobre teología adventista",
            message="Muéstrame libros y artículos sobre teología adventista publicados después de 2020",
        ),
    ]


@cl.on_chat_start
async def on_chat_start() -> None:
    """Inicializa una sesión nueva — Chainlit gestiona la persistencia via Data Layer."""
    cl.user_session.set("history", [])


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


def _render_citations(citations: list[dict]) -> str:
    """Sección simple de fuentes a partir de los `retriever_resource` de Dify.

    Dify devuelve document_name/content/score (y otros campos internos) por
    cada chunk recuperado — no hay bucketing por fuente institucional como en
    el GUIA legacy, así que listamos directo lo que llega.
    """
    if not citations:
        return ""
    lines = ["\n\n📚 **Fuentes consultadas**"]
    seen: set[str] = set()
    for c in citations:
        name = c.get("document_name") or c.get("dataset_name") or "Fuente"
        if name in seen:
            continue
        seen.add(name)
        score = c.get("score")
        score_txt = f" — *score {score:.2f}*" if isinstance(score, (int, float)) else ""
        lines.append(f"- {name}{score_txt}")
    return "\n".join(lines) + "\n"


@cl.on_message
async def on_message(message: cl.Message) -> None:
    """Procesa cada mensaje del usuario reenviándolo al sidecar de Dify.

    FASE A migración GUIA→Dify: Dify es el "cerebro" — routing, gates, RAG y
    síntesis viven ahí. GUIA solo reenvía la consulta y renderiza la
    respuesta. La memoria multi-turno la gestiona Dify vía `conversation_id`
    (guardado en `cl.user_session`); el `history` local ya NO se envía al LLM.
    """
    history: list[ConversationMessage] = cl.user_session.get("history", [])
    conversation_id: str = cl.user_session.get("dify_conversation_id", "")

    thinking_msg = cl.Message(content="")
    await thinking_msg.send()

    try:
        _user = cl.user_session.get("user")
        user_email = str(_user.identifier) if _user else "anon"

        result = await _dify_client.chat(
            query=message.content,
            user=user_email,
            conversation_id=conversation_id,
        )

        # Solo mostrar el step de retrieval cuando hubo citas reales
        if result.citations:
            rag_step = cl.Step(name="Búsqueda académica", type="retrieval")
            rag_step.input = message.content
            rag_step.output = f"{len(result.citations)} fuente(s) encontrada(s)"
            await rag_step.send()

        answer_text = result.answer + _render_citations(result.citations)

        thinking_msg.content = answer_text
        await thinking_msg.update()

        # Persistir el conversation_id de Dify para el siguiente turno
        cl.user_session.set("dify_conversation_id", result.conversation_id)

        # Stash de metadatos en Redis para que el DataLayer los recoja si el
        # usuario califica con 👍/👎. TTL 7 días — suficiente para feedback diferido.
        try:
            redis_client = getattr(_container, "redis_client", None)
            if redis_client is not None and thinking_msg.id:
                user = cl.user_session.get("user")
                stash_response_metadata(
                    redis_client,
                    str(thinking_msg.id),
                    query=message.content,
                    response=result.answer,
                    sources=result.citations,
                    intent=None,
                    model_used=result.ai_label.get("model") if result.ai_label else None,
                    user_id=str(getattr(user, "identifier", "anonymous")) if user else "anonymous",
                )
        except Exception:
            pass  # nunca romper la UX por el stash

        # Primer turno: generar título descriptivo para el thread en el sidebar
        if not history:
            title = await _generate_thread_title(message.content)
            try:
                from chainlit.data import get_data_layer as _get_dl
                dl = _get_dl()
                thread_id = getattr(cl.context.session, "thread_id", None)
                if dl and thread_id:
                    await dl.update_thread(thread_id=thread_id, name=title)
            except Exception:
                pass  # cosmético — no interrumpe la respuesta

        # Historial local en memoria de sesión — ya no alimenta al LLM (Dify
        # mantiene su propia memoria vía conversation_id), pero se conserva
        # para on_chat_resume/UI. Bounded a 20 mensajes = 10 turnos.
        history = history + [
            ConversationMessage(role="user", content=message.content),
            ConversationMessage(role="assistant", content=result.answer),
        ]
        cl.user_session.set("history", history[-20:])

    except DifyClientError as exc:
        logger.exception("dify_sidecar_error", exc_info=exc)
        thinking_msg.content = (
            "Lo siento, ocurrió un error consultando el asistente. "
            "Por favor, inténtalo de nuevo."
        )
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
    logger.info("chainlit_session_end", session_id=cl.context.session.id)
