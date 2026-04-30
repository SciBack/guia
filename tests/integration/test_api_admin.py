"""Tests del endpoint admin GET /api/admin/audit (P1.3 paso 3)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from guia.api.app import create_app
from guia.api.deps import get_audit_repo, get_container
from guia.audit import AuditLogEntry, AuditLogRepository
from guia.auth.identity import UserContext
from guia.config import GUIASettings, LLMMode


def _staff_user() -> UserContext:
    return UserContext(
        user_id="staff-uuid",
        email="admin@upeu.edu.pe",
        domain="upeu.edu.pe",
        roles=["staff", "audit-reader"],
        display_name="Admin User",
        is_staff=True,
    )


def _non_staff_user() -> UserContext:
    return UserContext(
        user_id="student-uuid",
        email="alumno@upeu.edu.pe",
        domain="upeu.edu.pe",
        roles=["student"],
        display_name="Student",
        is_staff=False,
    )


def _sample_entries() -> list[AuditLogEntry]:
    from datetime import UTC, datetime
    return [
        AuditLogEntry(
            user_id="target-user",
            session_id="sess-1",
            query_hash="aaaaaa",
            intent="research",
            privacy_level="cloud_ok",
            sources_used=["pgvector"],
            llm_model="claude-sonnet-4-7",
            llm_provider="anthropic-cloud",
            gate_used="embedding",
            latency_ms=2300,
            created_at=datetime(2026, 4, 30, 12, 0, 0, tzinfo=UTC),
        ),
        AuditLogEntry(
            user_id="target-user",
            session_id="sess-1",
            query_hash="bbbbbb",
            intent="campus",
            privacy_level="always_local",
            sources_used=["koha"],
            llm_model="qwen2.5:7b",
            llm_provider="ollama-local",
            gate_used="rules",
            latency_ms=180,
            created_at=datetime(2026, 4, 30, 12, 5, 0, tzinfo=UTC),
        ),
    ]


@pytest.fixture
def app_with_mocks() -> tuple[TestClient, MagicMock, MagicMock]:
    """TestClient con mocks de container, audit_repo e identity service."""
    settings = GUIASettings(
        guia_llm_mode=LLMMode.LOCAL,
        environment="development",
        redis_url="redis://localhost:6379/0",
    )
    app = create_app(settings)

    mock_container = MagicMock()
    mock_container.settings = settings

    # IdentityService es construido dentro del endpoint con app.state.container
    # Patcheamos el método verify_token via monkeypatch global del módulo
    mock_repo = MagicMock(spec=AuditLogRepository)
    mock_repo.get_by_user = AsyncMock(return_value=_sample_entries())

    app.state.container = mock_container
    app.state.settings = settings
    app.dependency_overrides[get_container] = lambda: mock_container
    app.dependency_overrides[get_audit_repo] = lambda: mock_repo

    return TestClient(app, raise_server_exceptions=True), mock_container, mock_repo


# ── Sin auth ──────────────────────────────────────────────────────────────


def test_audit_no_auth_returns_401(app_with_mocks: tuple) -> None:
    client, _, _ = app_with_mocks
    resp = client.get("/api/admin/audit?user_id=target-user")
    assert resp.status_code == 401


# ── Auth con role insuficiente ────────────────────────────────────────────


def test_audit_non_staff_returns_403(monkeypatch: pytest.MonkeyPatch, app_with_mocks: tuple) -> None:
    client, _, _ = app_with_mocks

    async def fake_verify(self, token: str) -> UserContext:
        return _non_staff_user()

    monkeypatch.setattr("guia.auth.identity.IdentityService.verify_token", fake_verify)

    resp = client.get(
        "/api/admin/audit?user_id=target-user",
        headers={"Authorization": "Bearer fake-token"},
    )
    assert resp.status_code == 403
    assert "staff" in resp.json()["detail"].lower()


# ── Auth con role staff ───────────────────────────────────────────────────


def test_audit_staff_returns_entries(
    monkeypatch: pytest.MonkeyPatch, app_with_mocks: tuple
) -> None:
    client, _, mock_repo = app_with_mocks

    async def fake_verify(self, token: str) -> UserContext:
        return _staff_user()

    monkeypatch.setattr("guia.auth.identity.IdentityService.verify_token", fake_verify)

    resp = client.get(
        "/api/admin/audit?user_id=target-user&limit=50",
        headers={"Authorization": "Bearer fake-token"},
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["user_id"] == "target-user"
    assert data["count"] == 2
    assert len(data["entries"]) == 2

    # Verificar que cada entry tiene query_hash y NO query
    for entry in data["entries"]:
        assert "query_hash" in entry
        assert "query" not in entry  # no leak
        assert "text" not in entry
        assert "prompt" not in entry

    # Repo recibe el limit correcto
    mock_repo.get_by_user.assert_called_once_with("target-user", limit=50)


def test_audit_staff_default_limit_100(
    monkeypatch: pytest.MonkeyPatch, app_with_mocks: tuple
) -> None:
    client, _, mock_repo = app_with_mocks

    async def fake_verify(self, token: str) -> UserContext:
        return _staff_user()

    monkeypatch.setattr("guia.auth.identity.IdentityService.verify_token", fake_verify)

    resp = client.get(
        "/api/admin/audit?user_id=target-user",
        headers={"Authorization": "Bearer fake-token"},
    )
    assert resp.status_code == 200
    mock_repo.get_by_user.assert_called_once_with("target-user", limit=100)


# ── Validación de parámetros ──────────────────────────────────────────────


def test_audit_missing_user_id_returns_422(
    monkeypatch: pytest.MonkeyPatch, app_with_mocks: tuple
) -> None:
    client, _, _ = app_with_mocks

    async def fake_verify(self, token: str) -> UserContext:
        return _staff_user()

    monkeypatch.setattr("guia.auth.identity.IdentityService.verify_token", fake_verify)

    resp = client.get(
        "/api/admin/audit",  # sin user_id
        headers={"Authorization": "Bearer fake-token"},
    )
    assert resp.status_code == 422


def test_audit_limit_out_of_range_returns_422(
    monkeypatch: pytest.MonkeyPatch, app_with_mocks: tuple
) -> None:
    client, _, _ = app_with_mocks

    async def fake_verify(self, token: str) -> UserContext:
        return _staff_user()

    monkeypatch.setattr("guia.auth.identity.IdentityService.verify_token", fake_verify)

    resp = client.get(
        "/api/admin/audit?user_id=u&limit=99999",  # > 1000
        headers={"Authorization": "Bearer fake-token"},
    )
    assert resp.status_code == 422
