"""Custom Chainlit DataLayer que captura feedback explícito (👍/👎).

Extiende SQLAlchemyDataLayer estándar de Chainlit para que cuando un usuario
rateá una respuesta, además de la persistencia normal de Chainlit, se guarde
en la tabla `chat_feedback` con todo el contexto (query+response+sources+
intent+model) — el dataset para fine-tuning.

Los metadatos transient (sources, intent, model) se rescatan de Redis donde
los dejó el chat_service tras generar la respuesta.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import redis
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.types import Feedback

from guia.feedback import ChatFeedback, ChatFeedbackRepository

logger = logging.getLogger(__name__)


def _meta_key(step_id: str) -> str:
    return f"guia:feedback_meta:{step_id}"


def stash_response_metadata(
    redis_client: redis.Redis,
    step_id: str,
    *,
    query: str,
    response: str,
    sources: list[dict[str, Any]],
    intent: str | None,
    model_used: str | None,
    user_id: str = "anonymous",
    pii_redacted: bool = False,
    ttl_seconds: int = 7 * 24 * 3600,
) -> None:
    """Guarda metadatos transient asociados a un step (mensaje del asistente).

    Llamado por chainlit_app.py después de update() del mensaje, cuando ya
    tenemos el step_id final de Chainlit. La data vive 7 días — si el usuario
    rateá después, todavía está disponible.
    """
    payload = {
        "query": query,
        "response": response,
        "sources": sources,
        "intent": intent,
        "model_used": model_used,
        "user_id": user_id,
        "pii_redacted": pii_redacted,
    }
    try:
        redis_client.setex(_meta_key(step_id), ttl_seconds, json.dumps(payload))
    except Exception:
        logger.warning("feedback_stash_failed", extra={"step_id": step_id})


class FeedbackCapturingDataLayer(SQLAlchemyDataLayer):
    """SQLAlchemyDataLayer + captura de 👍/👎 hacia chat_feedback.

    Mantiene el comportamiento estándar de Chainlit (la UI sigue funcionando
    igual: feedback se guarda en sus tablas internas para que el sidebar lo
    muestre). Adicionalmente, escribe a `chat_feedback` con todo el contexto
    para nuestro dataset.
    """

    def __init__(
        self,
        conninfo: str,
        feedback_repo: ChatFeedbackRepository,
        redis_client: redis.Redis,
        **kwargs: Any,
    ) -> None:
        super().__init__(conninfo=conninfo, **kwargs)
        self._feedback_repo = feedback_repo
        self._redis = redis_client

    async def upsert_feedback(self, feedback: Feedback) -> str:
        """Captura el feedback en nuestra tabla además del comportamiento default."""
        # 1. Persistencia normal de Chainlit (tablas feedbacks/steps internas)
        result = await super().upsert_feedback(feedback)

        # 2. Persistencia adicional al dataset chat_feedback
        try:
            await self._capture_to_dataset(feedback)
        except Exception:
            logger.exception("feedback_dataset_capture_failed")
            # No re-raise: el feedback de Chainlit ya quedó OK

        return result

    async def _capture_to_dataset(self, feedback: Feedback) -> None:
        step_id = getattr(feedback, "forId", None) or getattr(feedback, "for_id", None)
        thread_id = getattr(feedback, "threadId", None) or getattr(feedback, "thread_id", None)
        rating_raw = getattr(feedback, "value", 0)
        comment = getattr(feedback, "comment", None)

        if not step_id or not thread_id:
            logger.debug("feedback_skipped_missing_ids")
            return

        # Chainlit value ∈ {-1, 0, 1}. Solo persistimos valores explícitos.
        try:
            rating = int(rating_raw)
        except (TypeError, ValueError):
            return
        if rating not in (-1, 1):
            return  # 0 = sin opinión, no se guarda

        # Recuperar metadatos transient desde Redis
        meta = self._fetch_meta(step_id)
        if not meta:
            logger.warning("feedback_no_meta", extra={"step_id": step_id})
            return  # sin contexto no podemos armar entry útil

        fb = ChatFeedback(
            thread_id=str(thread_id),
            step_id=str(step_id),
            user_id=meta.get("user_id", "anonymous"),
            query=meta.get("query", ""),
            response=meta.get("response", ""),
            rating=rating,
            sources=meta.get("sources", []) or [],
            intent=meta.get("intent"),
            model_used=meta.get("model_used"),
            comment=comment,
            pii_redacted=bool(meta.get("pii_redacted", False)),
        )
        await self._feedback_repo.upsert(fb)
        logger.info(
            "feedback_captured",
            extra={"step_id": step_id, "rating": rating, "intent": fb.intent},
        )

    def _fetch_meta(self, step_id: str) -> dict[str, Any] | None:
        try:
            raw = self._redis.get(_meta_key(step_id))
            if not raw:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return json.loads(raw)
        except Exception:
            logger.warning("feedback_meta_fetch_failed", extra={"step_id": step_id})
            return None
