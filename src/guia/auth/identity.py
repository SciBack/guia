"""Capa de identidad de GUIA — ADR-034.

UserContext: dataclass con datos del usuario autenticado.
IdentityService: verifica tokens Keycloak y construye UserContext.

M3: usa sciback-identity-keycloak (KeycloakIdentityPort) para verificación.
El dominio permitido se configura via KEYCLOAK_ALLOWED_DOMAINS.
"""

from __future__ import annotations

from guia.logging import get_logger
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from guia.config import GUIASettings

logger = get_logger(__name__)

__all__ = ["IdentityService", "UserContext"]


@dataclass
class UserContext:
    """Contexto del usuario autenticado en una sesión GUIA.

    Campos siempre presentes (de Keycloak):
      ``user_id``, ``email``, ``domain``, ``roles``, ``display_name``, ``is_staff``.

    Campos enriquecidos por midPoint (opcional, ADR-034):
      ``institutional_id``, ``faculty``, ``program``, ``academic_phase``,
      ``advisor_id``, ``koha_patron_id``, ``sis_student_id``,
      ``erp_account_id``, ``moodle_user_id``, ``projects``, ``courses``.
    Vacíos si midPoint no está configurado o el usuario no existe en él.
    """

    user_id: str
    email: str
    domain: str
    roles: list[str] = field(default_factory=list)
    display_name: str = ""
    is_staff: bool = False
    # midPoint enrichment (vacío si no aplica)
    institutional_id: str | None = None
    faculty: str | None = None
    program: str | None = None
    academic_phase: str | None = None
    advisor_id: str | None = None
    koha_patron_id: str | None = None
    sis_student_id: str | None = None
    erp_account_id: str | None = None
    moodle_user_id: str | None = None
    projects: list[str] = field(default_factory=list)
    courses: list[str] = field(default_factory=list)

    @classmethod
    def anonymous(cls) -> UserContext:
        """UserContext para sesiones sin autenticación."""
        return cls(
            user_id="anonymous",
            email="",
            domain="",
            roles=[],
            display_name="Anónimo",
            is_staff=False,
        )

    @property
    def is_authenticated(self) -> bool:
        return self.user_id != "anonymous"

    @property
    def is_enriched(self) -> bool:
        """True si midPoint pobló al menos un campo institucional."""
        return any(
            v
            for v in (
                self.institutional_id,
                self.faculty,
                self.program,
                self.koha_patron_id,
                self.sis_student_id,
            )
        )


class IdentityService:
    """Verifica tokens Keycloak y construye UserContext.

    Usa sciback-identity-keycloak (KeycloakIdentityPort) como backend.
    Valida que el dominio del email esté en la lista permitida.

    Args:
        settings: GUIASettings con keycloak_allowed_domains.
    """

    def __init__(self, settings: GUIASettings) -> None:
        self._settings = settings
        self._allowed_domains = [
            d.strip().lower()
            for d in settings.keycloak_allowed_domains.split(",")
            if d.strip()
        ]
        self._keycloak_port = self._build_port()
        self._midpoint_enricher = self._build_enricher()

    def _build_port(self) -> object:
        """Construye KeycloakIdentityPort (lazy — puede fallar sin romper el app)."""
        try:
            from sciback_identity_keycloak import KeycloakIdentityPort, KeycloakSettings
            ks = KeycloakSettings(_env_file=None)
            return KeycloakIdentityPort(ks)
        except Exception as exc:
            logger.warning("keycloak_port_init_failed", exc=str(exc))
            return None

    def _build_enricher(self) -> object:
        """Construye MidPointIdentityEnricher si MIDPOINT_PASSWORD está seteado.

        Si midPoint no está configurado (default), devuelve None y
        verify_token() omite el enrichment. Esto mantiene a midPoint
        opt-in para no romper deploys que aún no lo necesiten.
        """
        password = getattr(self._settings, "midpoint_password", "") or ""
        if not password:
            logger.info("midpoint_enricher_skipped", reason="MIDPOINT_PASSWORD vacío")
            return None
        try:
            from sciback_identity_midpoint import (
                MidPointIdentityEnricher,
                MidPointSettings,
            )
            ms = MidPointSettings(
                url=self._settings.midpoint_url,  # type: ignore[attr-defined]
                username=self._settings.midpoint_username,  # type: ignore[attr-defined]
                password=password,
                cache_ttl=getattr(self._settings, "midpoint_cache_ttl", 900),
            )
            logger.info("midpoint_enricher_ready", url=ms.url, ttl=ms.cache_ttl)
            return MidPointIdentityEnricher(settings=ms)
        except Exception as exc:
            logger.warning("midpoint_enricher_init_failed", exc=str(exc))
            return None

    async def verify_token(self, token: str) -> UserContext:
        """Verifica el Bearer token y retorna UserContext.

        Args:
            token: JWT sin el prefijo "Bearer ".

        Returns:
            UserContext si el token es válido y el dominio está permitido.
            UserContext.anonymous() si el port no está disponible.

        Raises:
            PermissionError: Si el dominio del usuario no está en allowed_domains.
            ValueError: Si el token es inválido.
        """
        if self._keycloak_port is None:
            logger.warning("identity_service_no_keycloak_port")
            return UserContext.anonymous()

        try:
            # CanonicalUser de sciback-identity-keycloak
            canonical = await self._keycloak_port.verify_token(token)  # type: ignore[union-attr]

            email = str(getattr(canonical, "email", "") or "")
            domain = email.rsplit("@", maxsplit=1)[-1].lower() if "@" in email else ""

            # Validar dominio permitido
            if self._allowed_domains and domain not in self._allowed_domains:
                logger.warning(
                    "identity_domain_blocked",
                    domain=domain,
                    allowed=self._allowed_domains,
                )
                raise PermissionError(
                    f"Dominio @{domain} no autorizado en este nodo GUIA. "
                    f"Dominios permitidos: {', '.join(self._allowed_domains)}"
                )

            roles: list[str] = list(getattr(canonical, "roles", []) or [])
            display_name = str(
                getattr(canonical, "display_name", "")
                or getattr(canonical, "username", "")
                or email.split("@", maxsplit=1)[0]
            )

            # midPoint enrichment (best-effort — no rompe la auth si falla)
            if self._midpoint_enricher is not None:
                try:
                    canonical = await self._midpoint_enricher.enrich(canonical)  # type: ignore[union-attr]
                except Exception as exc:
                    logger.warning("midpoint_enrich_failed", exc=str(exc))

            return UserContext(
                user_id=str(canonical.id),
                email=email,
                domain=domain,
                roles=roles,
                display_name=display_name,
                is_staff=("staff" in roles or "admin" in roles),
                # midPoint fields (None si no enriched)
                institutional_id=getattr(canonical, "institutional_id", None),
                faculty=getattr(canonical, "faculty", None),
                program=getattr(canonical, "program", None),
                academic_phase=getattr(canonical, "academic_phase", None),
                advisor_id=getattr(canonical, "advisor_id", None),
                koha_patron_id=getattr(canonical, "koha_patron_id", None),
                sis_student_id=getattr(canonical, "sis_student_id", None),
                erp_account_id=getattr(canonical, "erp_account_id", None),
                moodle_user_id=getattr(canonical, "moodle_user_id", None),
                projects=list(getattr(canonical, "projects", []) or []),
                courses=list(getattr(canonical, "courses", []) or []),
            )

        except PermissionError:
            raise
        except Exception as exc:
            logger.warning("token_verification_failed", exc=str(exc))
            raise ValueError(f"Token inválido: {exc}") from exc

    def verify_token_sync(self, token: str) -> UserContext:
        """Versión sync de verify_token (usa asyncio.run — M3 bridge)."""
        import asyncio
        return asyncio.run(self.verify_token(token))
