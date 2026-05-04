"""Vinculación Telegram ↔ Keycloak — Sprint 0.5 Fase 2 (ADR-040).

Permite asociar un usuario de Telegram (telegram_user_id) con su identidad
Keycloak (sub UUID) para habilitar queries personales (notas, deudas,
préstamos) desde el bot.

Flujo:
  1. Usuario envía /vincular al bot → genera OTP 6 dígitos en Redis (TTL 10min).
  2. Usuario logueado en https://guia.upeu.edu.pe ingresa el OTP.
  3. Backend POST /api/auth/telegram/link valida Bearer Keycloak + OTP, crea
     binding en Postgres `guia_telegram_bindings`, borra OTP.
  4. Bot consulta `get_binding(telegram_user_id)` en cada query: si existe,
     enriquece la consulta con keycloak_sub para Personal-data routing.

Tabla:
  guia_telegram_bindings (
    telegram_user_id    BIGINT PRIMARY KEY,
    keycloak_sub        TEXT NOT NULL,
    telegram_username   TEXT,
    keycloak_email      TEXT,
    keycloak_username   TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at        TIMESTAMPTZ
  )

Redis OTP:
  Key:   guia:tg:otp:{code}        Value: JSON (telegram_user_id, username)
  Key:   guia:tg:otp:user:{tg_id}  Value: code  (índice inverso para revocar)
  TTL:   600s (10 min)
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis

logger = logging.getLogger(__name__)

__all__ = [
    "OTP_TTL_SECONDS",
    "TelegramBinding",
    "TelegramLinkRepository",
    "TelegramLinkService",
]

OTP_TTL_SECONDS = 600  # 10 minutos
_OTP_PREFIX = "guia:tg:otp:"
_OTP_USER_PREFIX = "guia:tg:otp:user:"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS guia_telegram_bindings (
    telegram_user_id    BIGINT PRIMARY KEY,
    keycloak_sub        TEXT NOT NULL,
    telegram_username   TEXT,
    keycloak_email      TEXT,
    keycloak_username   TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at        TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_guia_telegram_bindings_sub
    ON guia_telegram_bindings(keycloak_sub);
"""


@dataclass
class TelegramBinding:
    """Vínculo persistente entre un usuario Telegram y un sub Keycloak."""

    telegram_user_id: int
    keycloak_sub: str
    telegram_username: str | None = None
    keycloak_email: str | None = None
    keycloak_username: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = None


class TelegramLinkRepository:
    """Repositorio de bindings sobre Postgres (psycopg3 sync, async vía to_thread)."""

    def __init__(self, database_url: str) -> None:
        self._url = database_url
        self._conn: object | None = None

    def _connect(self) -> object:
        import psycopg
        url = self._url.replace("postgresql+psycopg://", "postgresql://")
        conn = psycopg.connect(url)
        conn.autocommit = True  # type: ignore[union-attr]
        return conn

    def initialize(self) -> None:
        """Abre conexión + crea tabla idempotente. Llamar al arrancar."""
        try:
            conn = self._connect()
            conn.execute(_CREATE_TABLE_SQL)  # type: ignore[union-attr]
            self._conn = conn
            logger.info("telegram_link_repository_ready")
        except Exception as exc:
            logger.warning("telegram_link_repository_init_failed", exc_info=exc)
            self._conn = None

    async def get_by_telegram_id(self, telegram_user_id: int) -> TelegramBinding | None:
        return await asyncio.to_thread(self._get_sync, telegram_user_id)

    async def upsert(self, binding: TelegramBinding) -> None:
        await asyncio.to_thread(self._upsert_sync, binding)

    async def delete_by_telegram_id(self, telegram_user_id: int) -> bool:
        return await asyncio.to_thread(self._delete_sync, telegram_user_id)

    async def touch_last_used(self, telegram_user_id: int) -> None:
        await asyncio.to_thread(self._touch_sync, telegram_user_id)

    # ── Sync impl ────────────────────────────────────────────────────────────

    def _get_sync(self, telegram_user_id: int) -> TelegramBinding | None:
        if self._conn is None:
            return None
        try:
            row = self._conn.execute(  # type: ignore[union-attr]
                "SELECT telegram_user_id, keycloak_sub, telegram_username, "
                "keycloak_email, keycloak_username, created_at, last_used_at "
                "FROM guia_telegram_bindings WHERE telegram_user_id = %s",
                (telegram_user_id,),
            ).fetchone()
            if row is None:
                return None
            return TelegramBinding(
                telegram_user_id=row[0],
                keycloak_sub=row[1],
                telegram_username=row[2],
                keycloak_email=row[3],
                keycloak_username=row[4],
                created_at=row[5],
                last_used_at=row[6],
            )
        except Exception as exc:
            logger.warning("telegram_binding_get_error", exc_info=exc)
            return None

    def _upsert_sync(self, b: TelegramBinding) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(  # type: ignore[union-attr]
                """
                INSERT INTO guia_telegram_bindings
                    (telegram_user_id, keycloak_sub, telegram_username,
                     keycloak_email, keycloak_username, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (telegram_user_id) DO UPDATE SET
                    keycloak_sub      = EXCLUDED.keycloak_sub,
                    telegram_username = EXCLUDED.telegram_username,
                    keycloak_email    = EXCLUDED.keycloak_email,
                    keycloak_username = EXCLUDED.keycloak_username
                """,
                (
                    b.telegram_user_id,
                    b.keycloak_sub,
                    b.telegram_username,
                    b.keycloak_email,
                    b.keycloak_username,
                    b.created_at,
                ),
            )
        except Exception as exc:
            logger.warning("telegram_binding_upsert_error", exc_info=exc)

    def _delete_sync(self, telegram_user_id: int) -> bool:
        if self._conn is None:
            return False
        try:
            row = self._conn.execute(  # type: ignore[union-attr]
                "DELETE FROM guia_telegram_bindings "
                "WHERE telegram_user_id = %s RETURNING telegram_user_id",
                (telegram_user_id,),
            ).fetchone()
            return row is not None
        except Exception as exc:
            logger.warning("telegram_binding_delete_error", exc_info=exc)
            return False

    def _touch_sync(self, telegram_user_id: int) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(  # type: ignore[union-attr]
                "UPDATE guia_telegram_bindings SET last_used_at = now() "
                "WHERE telegram_user_id = %s",
                (telegram_user_id,),
            )
        except Exception as exc:
            logger.warning("telegram_binding_touch_error", exc_info=exc)

    def close(self) -> None:
        if self._conn is not None:
            import contextlib
            with contextlib.suppress(Exception):
                self._conn.close()  # type: ignore[union-attr]
            self._conn = None


class TelegramLinkService:
    """Orquesta la vinculación: OTP en Redis + binding persistente en Postgres."""

    def __init__(
        self,
        repo: TelegramLinkRepository,
        redis_client: "redis.Redis",  # type: ignore[type-arg]
    ) -> None:
        self._repo = repo
        self._redis = redis_client

    # ── OTP generation (bot side) ────────────────────────────────────────────

    def generate_otp(
        self, telegram_user_id: int, telegram_username: str | None = None
    ) -> str:
        """Genera OTP 6 dígitos, lo guarda en Redis con TTL, revoca anteriores
        del mismo telegram_user_id.

        Returns:
            Código OTP de 6 dígitos.
        """
        # Revoca código previo del mismo usuario, si existe
        prev_key = f"{_OTP_USER_PREFIX}{telegram_user_id}"
        prev_code = self._redis.get(prev_key)
        if prev_code:
            prev_code_str = (
                prev_code.decode() if isinstance(prev_code, bytes) else str(prev_code)
            )
            self._redis.delete(f"{_OTP_PREFIX}{prev_code_str}")

        # Genera código (cripto-seguro, evita 0 inicial para no perder dígitos)
        code = f"{secrets.randbelow(900_000) + 100_000:06d}"
        payload = json.dumps(
            {
                "telegram_user_id": telegram_user_id,
                "telegram_username": telegram_username,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        self._redis.setex(f"{_OTP_PREFIX}{code}", OTP_TTL_SECONDS, payload)
        self._redis.setex(prev_key, OTP_TTL_SECONDS, code)
        logger.info(
            "telegram_otp_generated",
            extra={"telegram_user_id": telegram_user_id, "ttl_s": OTP_TTL_SECONDS},
        )
        return code

    # ── OTP consumption (web side, post-Keycloak auth) ───────────────────────

    async def consume_otp(
        self,
        code: str,
        keycloak_sub: str,
        keycloak_email: str | None = None,
        keycloak_username: str | None = None,
    ) -> TelegramBinding | None:
        """Consume un OTP y crea/actualiza el binding.

        Returns:
            TelegramBinding si el OTP era válido. None si expiró/no existe.
        """
        otp_key = f"{_OTP_PREFIX}{code}"
        raw = self._redis.get(otp_key)
        if not raw:
            return None
        try:
            data = json.loads(
                raw.decode() if isinstance(raw, bytes) else raw
            )
        except (ValueError, TypeError):
            return None

        telegram_user_id = int(data["telegram_user_id"])
        telegram_username = data.get("telegram_username")

        # Borra el OTP (single-use)
        self._redis.delete(otp_key)
        self._redis.delete(f"{_OTP_USER_PREFIX}{telegram_user_id}")

        binding = TelegramBinding(
            telegram_user_id=telegram_user_id,
            keycloak_sub=keycloak_sub,
            telegram_username=telegram_username,
            keycloak_email=keycloak_email,
            keycloak_username=keycloak_username,
        )
        await self._repo.upsert(binding)
        logger.info(
            "telegram_binding_created",
            extra={
                "telegram_user_id": telegram_user_id,
                "keycloak_sub": keycloak_sub,
            },
        )
        return binding

    # ── Lookup / management ──────────────────────────────────────────────────

    async def get_binding(self, telegram_user_id: int) -> TelegramBinding | None:
        """Recupera el binding (None si el usuario no está vinculado)."""
        return await self._repo.get_by_telegram_id(telegram_user_id)

    async def unlink(self, telegram_user_id: int) -> bool:
        """Borra el binding (el usuario o admin lo decide)."""
        return await self._repo.delete_by_telegram_id(telegram_user_id)

    async def touch(self, telegram_user_id: int) -> None:
        """Marca last_used_at = now() (best-effort, ignora errores)."""
        await self._repo.touch_last_used(telegram_user_id)
