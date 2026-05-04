"""Tests del wiring midPoint en IdentityService.

No tests reales contra midPoint — solo verificación de:
- Si MIDPOINT_PASSWORD vacío, enricher es None.
- Si enricher levanta excepción, auth NO se rompe (best-effort).
- Si enricher devuelve atributos, UserContext los expone.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from guia.auth.identity import IdentityService, UserContext


def _make_settings(midpoint_password: str = "") -> MagicMock:
    s = MagicMock()
    s.keycloak_allowed_domains = "upeu.edu.pe"
    s.midpoint_url = "http://midpoint:8080/midpoint"
    s.midpoint_username = "administrator"
    s.midpoint_password = midpoint_password
    s.midpoint_cache_ttl = 900
    return s


def test_user_context_anonymous_not_authenticated() -> None:
    u = UserContext.anonymous()
    assert not u.is_authenticated
    assert not u.is_enriched


def test_user_context_is_enriched_with_faculty() -> None:
    u = UserContext(
        user_id="x",
        email="a@upeu.edu.pe",
        domain="upeu.edu.pe",
        faculty="Facultad de Ingeniería",
    )
    assert u.is_authenticated
    assert u.is_enriched


def test_user_context_authenticated_but_not_enriched_yet() -> None:
    """Después de Keycloak pero antes/sin midPoint, is_enriched=False."""
    u = UserContext(user_id="x", email="a@upeu.edu.pe", domain="upeu.edu.pe")
    assert u.is_authenticated
    assert not u.is_enriched


def test_identity_service_no_password_no_enricher() -> None:
    """Sin MIDPOINT_PASSWORD, enricher debe ser None (opt-in)."""
    s = _make_settings(midpoint_password="")
    svc = IdentityService(s)
    assert svc._midpoint_enricher is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_verify_token_handles_enricher_failure() -> None:
    """Si enricher.enrich() levanta excepción, auth NO se rompe."""
    s = _make_settings(midpoint_password="x")
    svc = IdentityService(s)

    # Inyectar un keycloak_port falso que devuelve un canonical user
    fake_canonical = MagicMock()
    fake_canonical.id = "uuid-123"
    fake_canonical.email = "a@upeu.edu.pe"
    fake_canonical.username = "alberto"
    fake_canonical.display_name = "Alberto"
    fake_canonical.roles = ["user"]
    fake_canonical.institutional_id = None
    fake_canonical.faculty = None
    fake_canonical.program = None
    fake_canonical.academic_phase = None
    fake_canonical.advisor_id = None
    fake_canonical.koha_patron_id = None
    fake_canonical.sis_student_id = None
    fake_canonical.erp_account_id = None
    fake_canonical.moodle_user_id = None
    fake_canonical.projects = []
    fake_canonical.courses = []

    kc_port = MagicMock()
    kc_port.verify_token = AsyncMock(return_value=fake_canonical)
    svc._keycloak_port = kc_port  # noqa: SLF001

    # Enricher que falla
    enricher = MagicMock()
    enricher.enrich = AsyncMock(side_effect=RuntimeError("midpoint down"))
    svc._midpoint_enricher = enricher  # noqa: SLF001

    user = await svc.verify_token("fake.jwt.token")
    assert user.is_authenticated
    assert user.email == "a@upeu.edu.pe"
    # No enriched — pero auth no rompió
    assert not user.is_enriched


@pytest.mark.asyncio
async def test_verify_token_with_enricher_populates_fields() -> None:
    """Si enricher devuelve faculty/koha_patron_id, UserContext los expone."""
    s = _make_settings(midpoint_password="x")
    svc = IdentityService(s)

    canonical = MagicMock()
    canonical.id = "uuid-123"
    canonical.email = "a@upeu.edu.pe"
    canonical.username = "alberto"
    canonical.display_name = "Alberto"
    canonical.roles = ["user"]

    enriched = MagicMock()
    enriched.id = "uuid-123"
    enriched.email = "a@upeu.edu.pe"
    enriched.username = "alberto"
    enriched.display_name = "Alberto"
    enriched.roles = ["user"]
    enriched.institutional_id = "U-2020-12345"
    enriched.faculty = "Ingeniería"
    enriched.program = "Sistemas"
    enriched.academic_phase = "pregrado"
    enriched.advisor_id = "advisor-9"
    enriched.koha_patron_id = "PAT-456"
    enriched.sis_student_id = "SIS-789"
    enriched.erp_account_id = None
    enriched.moodle_user_id = "MDL-1"
    enriched.projects = ["proj-1"]
    enriched.courses = ["course-A"]

    kc_port = MagicMock()
    kc_port.verify_token = AsyncMock(return_value=canonical)
    svc._keycloak_port = kc_port  # noqa: SLF001

    enricher = MagicMock()
    enricher.enrich = AsyncMock(return_value=enriched)
    svc._midpoint_enricher = enricher  # noqa: SLF001

    user = await svc.verify_token("fake.jwt.token")
    assert user.is_authenticated
    assert user.is_enriched
    assert user.faculty == "Ingeniería"
    assert user.program == "Sistemas"
    assert user.koha_patron_id == "PAT-456"
    assert user.sis_student_id == "SIS-789"
    assert user.projects == ["proj-1"]
    assert user.courses == ["course-A"]
