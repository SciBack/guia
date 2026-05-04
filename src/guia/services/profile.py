"""UserProfile — perfil persistente del usuario en Postgres (M4 / ADR-034).

M3: datos de perfil solo en Redis (volátil).
M4: UserProfile persistido en Postgres vía SQLAlchemy.
    Redis sigue siendo la capa de sesión rápida (TTL corto).

Tabla: guia_user_profiles
  user_id        TEXT PRIMARY KEY  — UUID canónico de Keycloak
  email          TEXT NOT NULL
  domain         TEXT NOT NULL     — dominio del email (@upeu.edu.pe)
  display_name   TEXT
  opt_personalization BOOLEAN DEFAULT FALSE
  opt_analytics       BOOLEAN DEFAULT FALSE
  created_at     TIMESTAMPTZ DEFAULT now()
  updated_at     TIMESTAMPTZ DEFAULT now()
"""

from __future__ import annotations

import asyncio
from guia.logging import get_logger
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = get_logger(__name__)

__all__ = ["UserProfile", "UserProfileRepository"]

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS guia_user_profiles (
    user_id             TEXT PRIMARY KEY,
    email               TEXT NOT NULL,
    domain              TEXT NOT NULL,
    display_name        TEXT NOT NULL DEFAULT '',
    opt_personalization BOOLEAN NOT NULL DEFAULT FALSE,
    opt_analytics       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


@dataclass
class UserProfile:
    """Perfil persistente de un usuario GUIA.

    Attributes:
        user_id: UUID canónico (sub de Keycloak).
        email: Email institucional.
        domain: Dominio del email (ej: "upeu.edu.pe").
        display_name: Nombre visible.
        opt_personalization: Acepta personalización de resultados.
        opt_analytics: Acepta telemetría anónima.
        created_at: Primera vez que el usuario usó GUIA.
        updated_at: Última actualización del perfil.
    """

    user_id: str
    email: str
    domain: str
    display_name: str = ""
    opt_personalization: bool = False
    opt_analytics: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class UserProfileRepository:
    """Repositorio de perfiles de usuario sobre Postgres.

    Usa psycopg3 (mismo driver que pgvector) directamente sin ORM.
    Las operaciones bloqueantes se envuelven con asyncio.to_thread().

    Args:
        database_url: URL de conexión Postgres (postgresql+psycopg://...).
    """

    def __init__(self, database_url: str) -> None:
        self._url = database_url
        self._conn: object | None = None

    def _connect(self) -> object:
        """Abre conexión Postgres (sync, llamar desde to_thread)."""
        try:
            import psycopg
            # Convertir URL SQLAlchemy → psycopg3
            url = self._url.replace("postgresql+psycopg://", "postgresql://")
            conn = psycopg.connect(url)
            conn.autocommit = True  # type: ignore[union-attr]
            return conn
        except ImportError:
            logger.error("psycopg not installed — UserProfileRepository unavailable")
            raise

    def _ensure_table(self, conn: object) -> None:
        """Crea la tabla si no existe (idempotente)."""
        conn.execute(_CREATE_TABLE_SQL)  # type: ignore[union-attr]

    def initialize(self) -> None:
        """Inicializa la conexión y crea la tabla. Llamar al arrancar la app."""
        try:
            conn = self._connect()
            self._ensure_table(conn)
            self._conn = conn
            logger.info("user_profile_repository_ready")
        except Exception as exc:
            logger.warning("user_profile_repository_init_failed", exc=str(exc))
            self._conn = None

    # ── Operaciones async (para uso desde ChatService y endpoints) ─────────────

    async def get(self, user_id: str) -> UserProfile | None:
        """Obtiene el perfil del usuario, o None si no existe."""
        return await asyncio.to_thread(self._get_sync, user_id)

    async def upsert(self, profile: UserProfile) -> None:
        """Crea o actualiza el perfil del usuario."""
        await asyncio.to_thread(self._upsert_sync, profile)

    async def update_opt_ins(
        self,
        user_id: str,
        *,
        personalization: bool | None = None,
        analytics: bool | None = None,
    ) -> None:
        """Actualiza solo los opt-ins del usuario."""
        await asyncio.to_thread(
            self._update_opt_ins_sync, user_id, personalization, analytics
        )

    async def delete(self, user_id: str) -> bool:
        """Elimina el perfil del usuario. Retorna True si existía."""
        return await asyncio.to_thread(self._delete_sync, user_id)

    # ── Implementaciones sync (ejecutadas en thread pool) ──────────────────────

    def _get_sync(self, user_id: str) -> UserProfile | None:
        if self._conn is None:
            return None
        try:
            row = self._conn.execute(  # type: ignore[union-attr]
                "SELECT user_id, email, domain, display_name, "
                "opt_personalization, opt_analytics, created_at, updated_at "
                "FROM guia_user_profiles WHERE user_id = %s",
                (user_id,),
            ).fetchone()
            if row is None:
                return None
            return UserProfile(
                user_id=row[0],
                email=row[1],
                domain=row[2],
                display_name=row[3],
                opt_personalization=row[4],
                opt_analytics=row[5],
                created_at=row[6],
                updated_at=row[7],
            )
        except Exception as exc:
            logger.warning("profile_get_error", user_id=user_id, exc=str(exc))
            return None

    def _upsert_sync(self, profile: UserProfile) -> None:
        if self._conn is None:
            return
        try:
            now = datetime.now(UTC)
            self._conn.execute(  # type: ignore[union-attr]
                """
                INSERT INTO guia_user_profiles
                    (user_id, email, domain, display_name,
                     opt_personalization, opt_analytics, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    email = EXCLUDED.email,
                    domain = EXCLUDED.domain,
                    display_name = EXCLUDED.display_name,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    profile.user_id,
                    profile.email,
                    profile.domain,
                    profile.display_name,
                    profile.opt_personalization,
                    profile.opt_analytics,
                    profile.created_at,
                    now,
                ),
            )
            logger.debug("profile_upserted", user_id=profile.user_id)
        except Exception as exc:
            logger.warning("profile_upsert_error", user_id=profile.user_id, exc=str(exc))

    def _update_opt_ins_sync(
        self,
        user_id: str,
        personalization: bool | None,
        analytics: bool | None,
    ) -> None:
        if self._conn is None:
            return
        try:
            fields: list[str] = ["updated_at = now()"]
            values: list[object] = []
            if personalization is not None:
                fields.append("opt_personalization = %s")
                values.append(personalization)
            if analytics is not None:
                fields.append("opt_analytics = %s")
                values.append(analytics)
            values.append(user_id)
            self._conn.execute(  # type: ignore[union-attr]
                f"UPDATE guia_user_profiles SET {', '.join(fields)} WHERE user_id = %s",
                values,
            )
        except Exception as exc:
            logger.warning("profile_opt_ins_error", user_id=user_id, exc=str(exc))

    def _delete_sync(self, user_id: str) -> bool:
        if self._conn is None:
            return False
        try:
            result = self._conn.execute(  # type: ignore[union-attr]
                "DELETE FROM guia_user_profiles WHERE user_id = %s RETURNING user_id",
                (user_id,),
            )
            return result.fetchone() is not None
        except Exception as exc:
            logger.warning("profile_delete_error", user_id=user_id, exc=str(exc))
            return False

    def close(self) -> None:
        """Cierra la conexión Postgres."""
        if self._conn is not None:
            import contextlib
            with contextlib.suppress(Exception):
                self._conn.close()  # type: ignore[union-attr]
            self._conn = None
