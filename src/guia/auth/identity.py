"""Capa de identidad de GUIA — ADR-034.

UserContext: dataclass con datos del usuario autenticado.
IdentityService: verifica tokens Keycloak y construye UserContext.

M3: usa sciback-identity-keycloak (KeycloakIdentityPort) para verificación.
El dominio permitido se configura via KEYCLOAK_ALLOWED_DOMAINS.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from guia.config import GUIASettings

logger = logging.getLogger(__name__)

__all__ = ["IdentityService", "UserContext"]


@dataclass
class UserContext:
    """Contexto del usuario autenticado en una sesión GUIA.

    Attributes:
        user_id: UUID canónico derivado del sub de Keycloak.
        email: Email institucional del usuario.
        domain: Dominio extraído del email (ej: "upeu.edu.pe").
        roles: Roles del realm Keycloak.
        display_name: Nombre visible (preferred_username o full_name).
        is_staff: True si tiene rol staff o admin.
    """

    user_id: str
    email: str
    domain: str
    roles: list[str] = field(default_factory=list)
    display_name: str = ""
    is_staff: bool = False

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

    def _build_port(self) -> object:
        """Construye KeycloakIdentityPort (lazy — puede fallar sin romper el app)."""
        try:
            from sciback_identity_keycloak import KeycloakIdentityPort, KeycloakSettings
            ks = KeycloakSettings(_env_file=None)
            return KeycloakIdentityPort(ks)
        except Exception as exc:
            logger.warning("keycloak_port_init_failed", exc=str(exc))
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

            return UserContext(
                user_id=str(canonical.id),
                email=email,
                domain=domain,
                roles=roles,
                display_name=display_name,
                is_staff=("staff" in roles or "admin" in roles),
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
