"""ConversationRepository — historial de chat persistido en Postgres.

Tabla chat_sessions: una fila por sesión Chainlit/Telegram.
Tabla chat_messages: cada turno (user + assistant) de la conversación.

Mismo patrón de conexión que UserProfileRepository (psycopg3 sync + to_thread).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

__all__ = ["StoredMessage", "ConversationRepository"]

_MIGRATE_SQL = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT,
    email       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id  TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        VARCHAR(10) NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    intent      VARCHAR(20),
    model_used  VARCHAR(80),
    cached      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_email   ON chat_sessions(email, updated_at DESC);
"""


@dataclass(frozen=True)
class StoredMessage:
    """Mensaje almacenado en Postgres."""

    role: str
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    intent: str | None = None
    model_used: str | None = None
    cached: bool = False


class ConversationRepository:
    """Repositorio de historial de conversaciones sobre Postgres.

    Args:
        database_url: URL de conexión (postgresql+psycopg://...).
        history_limit: Máximo de mensajes a devolver por sesión (default 20 = 10 turnos).
    """

    def __init__(self, database_url: str, *, history_limit: int = 20) -> None:
        self._url = database_url
        self._history_limit = history_limit
        self._conn: object | None = None

    def initialize(self) -> None:
        """Crea tablas si no existen y abre conexión. Llamar al arrancar."""
        try:
            import psycopg
            url = self._url.replace("postgresql+psycopg://", "postgresql://")
            conn = psycopg.connect(url)
            conn.autocommit = True  # type: ignore[union-attr]
            conn.execute(_MIGRATE_SQL)  # type: ignore[union-attr]
            self._conn = conn
            logger.info("conversation_repository_ready")
        except Exception as exc:
            logger.warning("conversation_repository_init_failed", exc_info=exc)
            self._conn = None

    # ── API async ──────────────────────────────────────────────────────────────

    async def ensure_session(
        self, session_id: str, *, user_id: str | None = None, email: str | None = None
    ) -> None:
        """Crea la sesión si no existe (idempotente)."""
        await asyncio.to_thread(self._ensure_session_sync, session_id, user_id, email)

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        intent: str | None = None,
        model_used: str | None = None,
        cached: bool = False,
    ) -> None:
        """Persiste un mensaje en la sesión."""
        await asyncio.to_thread(
            self._save_message_sync, session_id, role, content, intent, model_used, cached
        )

    async def get_history(
        self, session_id: str, *, limit: int | None = None
    ) -> list[StoredMessage]:
        """Devuelve los últimos mensajes de la sesión, del más antiguo al más reciente."""
        return await asyncio.to_thread(
            self._get_history_sync, session_id, limit or self._history_limit
        )

    async def get_user_history(
        self, email: str, *, limit: int | None = None
    ) -> list[StoredMessage]:
        """Devuelve los últimos mensajes de todas las sesiones de un usuario."""
        return await asyncio.to_thread(
            self._get_user_history_sync, email, limit or self._history_limit
        )

    # ── Implementaciones sync ──────────────────────────────────────────────────

    def _ensure_session_sync(
        self, session_id: str, user_id: str | None, email: str | None
    ) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(  # type: ignore[union-attr]
                """
                INSERT INTO chat_sessions (id, user_id, email)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    updated_at = NOW(),
                    user_id = COALESCE(EXCLUDED.user_id, chat_sessions.user_id),
                    email   = COALESCE(EXCLUDED.email,   chat_sessions.email)
                """,
                (session_id, user_id, email),
            )
        except Exception as exc:
            logger.warning("ensure_session_error", session_id=session_id, exc_info=exc)

    def _save_message_sync(
        self,
        session_id: str,
        role: str,
        content: str,
        intent: str | None,
        model_used: str | None,
        cached: bool,
    ) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(  # type: ignore[union-attr]
                """
                INSERT INTO chat_messages
                    (session_id, role, content, intent, model_used, cached)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (session_id, role, content, intent, model_used, cached),
            )
        except Exception as exc:
            logger.warning("save_message_error", session_id=session_id, exc_info=exc)

    def _get_history_sync(self, session_id: str, limit: int) -> list[StoredMessage]:
        if self._conn is None:
            return []
        try:
            rows = self._conn.execute(  # type: ignore[union-attr]
                """
                SELECT role, content, intent, model_used, cached, created_at
                FROM (
                    SELECT role, content, intent, model_used, cached, created_at
                    FROM chat_messages
                    WHERE session_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                ) sub
                ORDER BY created_at ASC
                """,
                (session_id, limit),
            ).fetchall()
            return [
                StoredMessage(
                    role=r[0], content=r[1], intent=r[2],
                    model_used=r[3], cached=r[4], created_at=r[5],
                )
                for r in rows
            ]
        except Exception as exc:
            logger.warning("get_history_error", session_id=session_id, exc_info=exc)
            return []

    def _get_user_history_sync(self, email: str, limit: int) -> list[StoredMessage]:
        if self._conn is None:
            return []
        try:
            rows = self._conn.execute(  # type: ignore[union-attr]
                """
                SELECT role, content, intent, model_used, cached, created_at
                FROM (
                    SELECT m.role, m.content, m.intent, m.model_used, m.cached, m.created_at
                    FROM chat_messages m
                    JOIN chat_sessions s ON s.id = m.session_id
                    WHERE s.email = %s
                    ORDER BY m.created_at DESC
                    LIMIT %s
                ) sub
                ORDER BY created_at ASC
                """,
                (email, limit),
            ).fetchall()
            return [
                StoredMessage(
                    role=r[0], content=r[1], intent=r[2],
                    model_used=r[3], cached=r[4], created_at=r[5],
                )
                for r in rows
            ]
        except Exception as exc:
            logger.warning("get_user_history_error", email=email, exc_info=exc)
            return []

    def close(self) -> None:
        if self._conn is not None:
            import contextlib
            with contextlib.suppress(Exception):
                self._conn.close()  # type: ignore[union-attr]
            self._conn = None
