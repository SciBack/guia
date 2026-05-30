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
from starlette.types import ASGIApp, Receive, Scope, Send

from sciback_core.ports.llm import LLMMessage

from guia.channels.feedback_datalayer import (
    FeedbackCapturingDataLayer,
    stash_response_metadata,
)
from guia.config import GUIASettings
from guia.container import GUIAContainer
from guia.channels.render import render_results_list
from guia.domain.chat import ChatRequest, ConversationMessage
from guia.logging import configure_logging, get_logger

_settings = GUIASettings()
configure_logging(level=_settings.log_level, json_logs=False)
logger = get_logger(__name__)

_container = GUIAContainer(_settings)


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
    """Pre-calienta routers y modelos NLP al arrancar.

    Routers (warm_up): bloqueantes — deben completar antes de aceptar
    requests para que el primer mensaje no sufra el cold-start de embeddings.

    Gates NLP (lid.176.bin + detoxify): CPU-bound y potencialmente lentos en
    la PRIMERA descarga (lid ~25s, detoxify ~1.1GB). Se lanzan como tarea
    background (fire-and-forget) para no retrasar /healthz más allá del timeout
    del healthcheck. Tras persistir en el volumen fastembed_cache/torch_cache,
    los reinicios posteriores solo cargan de disco. Ver
    incident_chainlit_coldstart_socket en memoria.
    """
    router = getattr(_container, "router", None)
    if router is not None:
        logger.info("model_router_warmup_start")
        await router.warm_up()
        logger.info("model_router_warmup_done")

    cascade = getattr(_container, "cascade_router", None)
    if cascade is not None:
        logger.info("cascade_router_warmup_start")
        await cascade.warm_up()
        logger.info("cascade_router_warmup_done")

    # Gates NLP: fire-and-forget en background (no bloquea startup ni /healthz).
    asyncio.create_task(_warmup_nlp_gates())


async def _warmup_nlp_gates() -> None:
    """Carga lid.176.bin (LanguageGate) y Detoxify multilingual (ToxicityGate)
    en threads separados, para que estén calientes antes del primer mensaje
    del usuario en vez de cargarse de forma lazy en la primera query (~25s).

    Errores de carga no tumban el proceso — los gates tienen fallback seguro
    incorporado (lid → ("es", 1.0), toxicity → score 0.0).
    """
    # lid.176.bin — LanguageGate
    try:
        logger.info("nlp_warmup_lid_start")
        from guia.nlp.language import detect_language
        await asyncio.to_thread(detect_language, "warmup")
        logger.info("nlp_warmup_lid_done")
    except Exception:
        logger.warning("nlp_warmup_lid_failed", exc_info=True)

    # Detoxify multilingual — ToxicityGate.
    # Se invoca sobre la instancia del container para respetar enabled/threshold
    # de settings. Si toxicity está disabled, evaluate() retorna sin cargar pesos.
    toxicity_gate = getattr(_container, "toxicity_gate", None)
    if toxicity_gate is not None:
        try:
            logger.info("nlp_warmup_toxicity_start")
            await asyncio.to_thread(toxicity_gate.evaluate, "warmup query")
            logger.info("nlp_warmup_toxicity_done")
        except Exception:
            logger.warning("nlp_warmup_toxicity_failed", exc_info=True)


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


@cl.on_message
async def on_message(message: cl.Message) -> None:
    """Procesa cada mensaje del usuario."""
    history: list[ConversationMessage] = cl.user_session.get("history", [])

    thinking_msg = cl.Message(content="")
    await thinking_msg.send()

    try:
        # user_id (email del usuario autenticado) habilita el bucketing del
        # AgentOrchestrator (ADR-050) también en web. Anónimos → None → legacy.
        _user = cl.user_session.get("user")
        request = ChatRequest(
            query=message.content,
            user_id=str(_user.identifier) if _user else None,
            session_id=cl.context.session.id,
            language="es",
            history=history,
        )

        response = await _container.chat_service.answer(request)

        # Solo mostrar el step de retrieval cuando hubo búsqueda académica real
        if response.sources or response.cached:
            rag_step = cl.Step(name="Búsqueda académica", type="retrieval")
            rag_step.input = message.content
            rag_step.output = (
                "Caché semántico"
                if response.cached
                else f"{len(response.sources)} fuente(s) académica(s) encontrada(s)"
            )
            await rag_step.send()

        answer_text = response.answer
        elements: list[cl.Element] = []
        for source in response.sources:
            if source.url and source.url.lower().endswith(".pdf"):
                elements.append(
                    cl.Pdf(name=source.title[:50], url=source.url, display="side")
                )

        # Render de citas según el tipo de respuesta (derivado en ChatService):
        # - "list"      → cada resultado es un enlace inline; el listado SUSTITUYE
        #                 la prosa del LLM (que repetía los títulos sin enlace).
        # - "narrative" → prosa + sección "Fuente consultada" al final (como antes).
        if response.answer_type == "list" and response.sources:
            answer_text = render_results_list(response)
        elif response.source_buckets:
            # Índice de fuentes por source_type para cruzar con sources individuales
            sources_by_type: dict[str, list] = {}
            for s in response.sources:
                key = s.source_type or "unknown"
                sources_by_type.setdefault(key, []).append(s)

            answer_text += "\n\n📚 **Fuente consultada**\n"
            for bucket in response.source_buckets:
                answer_text += f"\n**[{bucket.label}]({bucket.url})**\n"
                for s in sources_by_type.get(bucket.source_type, []):
                    title_link = f"[{s.title}]({s.url})" if s.url else s.title
                    meta_parts = []
                    if s.authors:
                        meta_parts.append(", ".join(s.authors[:2]))
                    if s.year:
                        meta_parts.append(str(s.year))
                    meta = f" — *{' · '.join(meta_parts)}*" if meta_parts else ""
                    answer_text += f"- {title_link}{meta}\n"

        if response.explore_in:
            answer_text += "\n🔎 **Explora también este tema en**\n"
            for link in response.explore_in:
                tag = "" if link.available else " *(pendiente de habilitar en GUIA)*"
                answer_text += f"- [{link.label}]({link.url}){tag}\n"

        if response.related_terms:
            terms = " · ".join(response.related_terms)
            answer_text += f"\n💡 **Búsquedas relacionadas:** {terms}\n"

        if response.cached:
            answer_text += "\n\n*Respuesta desde caché semántico*"

        thinking_msg.content = answer_text
        if elements:
            thinking_msg.elements = elements
        await thinking_msg.update()

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
                    response=response.answer,
                    sources=[s.model_dump() for s in response.sources],
                    intent=str(response.intent.value) if response.intent else None,
                    model_used=response.model_used,
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
