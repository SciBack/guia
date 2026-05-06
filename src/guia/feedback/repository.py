"""ChatFeedbackRepository — persistencia + export del dataset de feedback."""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from guia.feedback.models import ChatFeedback

logger = logging.getLogger(__name__)


_MIGRATE_SQL = """
CREATE TABLE IF NOT EXISTS chat_feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id       TEXT NOT NULL,
    step_id         TEXT NOT NULL,
    user_id         TEXT NOT NULL DEFAULT 'anonymous',
    query           TEXT NOT NULL,
    response        TEXT NOT NULL,
    rating          SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
    sources         JSONB NOT NULL DEFAULT '[]'::jsonb,
    intent          TEXT,
    model_used      TEXT,
    comment         TEXT,
    pii_redacted    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (thread_id, step_id)
);

CREATE INDEX IF NOT EXISTS idx_feedback_created   ON chat_feedback(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_rating    ON chat_feedback(rating, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_user      ON chat_feedback(user_id, created_at DESC);
"""


class ChatFeedbackRepository:
    """Repositorio del dataset de feedback.

    Patrón consistente con AuditLogRepository: psycopg3 sync + asyncio.to_thread().
    Si la conexión falla, las llamadas son no-op (warning) — el feedback es
    importante para el dataset pero no debe romper la UX.
    """

    def __init__(self, database_url: str) -> None:
        self._url = database_url
        self._conn: object | None = None

    def initialize(self) -> None:
        """Crea la tabla si no existe y abre conexión."""
        try:
            import psycopg
            url = self._url.replace("postgresql+psycopg://", "postgresql://")
            conn = psycopg.connect(url)
            conn.autocommit = True  # type: ignore[union-attr]
            conn.execute(_MIGRATE_SQL)  # type: ignore[union-attr]
            self._conn = conn
            logger.info("chat_feedback_repository_ready")
        except Exception as exc:
            logger.warning("chat_feedback_repository_init_failed", exc_info=exc)
            self._conn = None

    # ── API async ─────────────────────────────────────────────────────────

    async def upsert(self, fb: ChatFeedback) -> None:
        """Inserta o actualiza una entrada (clave única: thread_id+step_id).

        Si el usuario cambia de 👍 a 👎 (o viceversa), se actualiza el rating.
        """
        await asyncio.to_thread(self._upsert_sync, fb)

    async def export_jsonl(
        self,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> Iterator[str]:
        """Genera líneas JSONL del rango de fechas indicado.

        Cada línea es un objeto JSON listo para fine-tuning o análisis.
        """
        rows = await asyncio.to_thread(self._select_range_sync, from_dt, to_dt)
        for row in rows:
            yield json.dumps(row, ensure_ascii=False, default=str)

    async def count(self) -> int:
        """Total de entradas en el dataset."""
        return await asyncio.to_thread(self._count_sync)

    async def stats(self) -> dict[str, int]:
        """Estadísticas básicas del dataset."""
        return await asyncio.to_thread(self._stats_sync)

    # ── Sync ──────────────────────────────────────────────────────────────

    def _upsert_sync(self, fb: ChatFeedback) -> None:
        if self._conn is None:
            return
        if fb.rating not in (-1, 1):
            logger.warning("feedback_invalid_rating", rating=fb.rating)
            return
        try:
            self._conn.execute(  # type: ignore[union-attr]
                """
                INSERT INTO chat_feedback
                  (thread_id, step_id, user_id, query, response, rating,
                   sources, intent, model_used, comment, pii_redacted, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
                ON CONFLICT (thread_id, step_id) DO UPDATE SET
                  rating = EXCLUDED.rating,
                  comment = EXCLUDED.comment,
                  created_at = NOW()
                """,
                (
                    fb.thread_id,
                    fb.step_id,
                    fb.user_id,
                    fb.query,
                    fb.response,
                    fb.rating,
                    json.dumps(fb.sources, ensure_ascii=False),
                    fb.intent,
                    fb.model_used,
                    fb.comment,
                    fb.pii_redacted,
                    fb.created_at,
                ),
            )
        except Exception:
            logger.exception("feedback_upsert_failed")

    def _select_range_sync(
        self,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> list[dict[str, Any]]:
        if self._conn is None:
            return []
        clauses = []
        params: list[Any] = []
        if from_dt is not None:
            clauses.append("created_at >= %s")
            params.append(from_dt)
        if to_dt is not None:
            clauses.append("created_at < %s")
            params.append(to_dt)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
            SELECT thread_id, step_id, user_id, query, response, rating,
                   sources, intent, model_used, comment, pii_redacted,
                   created_at
            FROM chat_feedback
            {where}
            ORDER BY created_at ASC
        """
        try:
            cur = self._conn.execute(sql, params)  # type: ignore[union-attr]
            cols = [d.name for d in cur.description] if cur.description else []
            return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]
        except Exception:
            logger.exception("feedback_export_failed")
            return []

    def _count_sync(self) -> int:
        if self._conn is None:
            return 0
        try:
            cur = self._conn.execute("SELECT COUNT(*) FROM chat_feedback")  # type: ignore[union-attr]
            row = cur.fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def _stats_sync(self) -> dict[str, int]:
        if self._conn is None:
            return {"total": 0, "positive": 0, "negative": 0}
        try:
            cur = self._conn.execute(  # type: ignore[union-attr]
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) AS positive,
                    SUM(CASE WHEN rating = -1 THEN 1 ELSE 0 END) AS negative
                FROM chat_feedback
                """
            )
            row = cur.fetchone()
            if not row:
                return {"total": 0, "positive": 0, "negative": 0}
            return {
                "total": int(row[0] or 0),
                "positive": int(row[1] or 0),
                "negative": int(row[2] or 0),
            }
        except Exception:
            return {"total": 0, "positive": 0, "negative": 0}
