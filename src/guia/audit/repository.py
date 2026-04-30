"""AuditLogRepository — persistencia en Postgres (ADR-036)."""

from __future__ import annotations

import asyncio
import logging

from guia.audit.models import AuditLogEntry

logger = logging.getLogger(__name__)


_MIGRATE_SQL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    session_id      TEXT,
    query_hash      TEXT NOT NULL,
    intent          TEXT NOT NULL,
    privacy_level   TEXT NOT NULL,
    sources_used    TEXT[] NOT NULL DEFAULT '{}',
    llm_model       TEXT NOT NULL,
    llm_provider    TEXT NOT NULL,
    gate_used       TEXT NOT NULL DEFAULT 'unknown',
    pii_detected    BOOLEAN NOT NULL DEFAULT FALSE,
    pii_redacted    BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    cached          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_user_created ON audit_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_provider     ON audit_log(llm_provider, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_query_hash   ON audit_log(query_hash);
"""


class AuditLogRepository:
    """Repositorio de audit log (ADR-036).

    Patrón idéntico a ConversationRepository: psycopg3 sync + asyncio.to_thread().
    Si la conexión falla al inicializar, las llamadas posteriores son no-op
    (logging warning) — el audit es importante pero no debe romper la app.

    Args:
        database_url: URL de conexión (postgresql+psycopg://...).
    """

    def __init__(self, database_url: str) -> None:
        self._url = database_url
        self._conn: object | None = None

    def initialize(self) -> None:
        """Crea la tabla si no existe y abre conexión. Llamar al arrancar."""
        try:
            import psycopg
            url = self._url.replace("postgresql+psycopg://", "postgresql://")
            conn = psycopg.connect(url)
            conn.autocommit = True  # type: ignore[union-attr]
            conn.execute(_MIGRATE_SQL)  # type: ignore[union-attr]
            self._conn = conn
            logger.info("audit_log_repository_ready")
        except Exception as exc:
            logger.warning("audit_log_repository_init_failed", exc_info=exc)
            self._conn = None

    # ── API async ─────────────────────────────────────────────────────────

    async def record(self, entry: AuditLogEntry) -> None:
        """Persiste una entrada de audit (fire-and-forget, errores logueados)."""
        await asyncio.to_thread(self._record_sync, entry)

    async def get_by_user(
        self, user_id: str, *, limit: int = 100
    ) -> list[AuditLogEntry]:
        """Devuelve entradas recientes de un usuario, más reciente primero."""
        return await asyncio.to_thread(self._get_by_user_sync, user_id, limit)

    # ── Sync ──────────────────────────────────────────────────────────────

    def _record_sync(self, entry: AuditLogEntry) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(  # type: ignore[union-attr]
                """
                INSERT INTO audit_log
                  (user_id, session_id, query_hash, intent, privacy_level,
                   sources_used, llm_model, llm_provider, gate_used,
                   pii_detected, pii_redacted, latency_ms, cached)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    entry.user_id,
                    entry.session_id,
                    entry.query_hash,
                    entry.intent,
                    entry.privacy_level,
                    entry.sources_used,
                    entry.llm_model,
                    entry.llm_provider,
                    entry.gate_used,
                    entry.pii_detected,
                    entry.pii_redacted,
                    entry.latency_ms,
                    entry.cached,
                ),
            )
        except Exception as exc:
            logger.warning("audit_record_error", exc_info=exc)

    def _get_by_user_sync(self, user_id: str, limit: int) -> list[AuditLogEntry]:
        if self._conn is None:
            return []
        try:
            rows = self._conn.execute(  # type: ignore[union-attr]
                """
                SELECT user_id, session_id, query_hash, intent, privacy_level,
                       sources_used, llm_model, llm_provider, gate_used,
                       pii_detected, pii_redacted, latency_ms, cached, created_at
                FROM audit_log
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            ).fetchall()
            return [
                AuditLogEntry(
                    user_id=r[0],
                    session_id=r[1],
                    query_hash=r[2],
                    intent=r[3],
                    privacy_level=r[4],
                    sources_used=list(r[5]) if r[5] else [],
                    llm_model=r[6],
                    llm_provider=r[7],
                    gate_used=r[8],
                    pii_detected=r[9],
                    pii_redacted=r[10],
                    latency_ms=r[11],
                    cached=r[12],
                    created_at=r[13],
                )
                for r in rows
            ]
        except Exception as exc:
            logger.warning("audit_get_by_user_error", exc_info=exc)
            return []

    def close(self) -> None:
        if self._conn is not None:
            import contextlib
            with contextlib.suppress(Exception):
                self._conn.close()  # type: ignore[union-attr]
            self._conn = None
