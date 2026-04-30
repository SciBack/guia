"""Tests del wire-up de GROBID en GUIAContainer (config + fallback)."""

from __future__ import annotations

import pytest

from guia.config import GUIASettings


def test_grobid_url_default_is_empty() -> None:
    """Por default GROBID está deshabilitado (vacío)."""
    s = GUIASettings(_env_file=None)
    assert s.grobid_url == ""


def test_grobid_url_can_be_set_via_settings() -> None:
    s = GUIASettings(_env_file=None, grobid_url="http://grobid:8070")
    assert s.grobid_url == "http://grobid:8070"


def test_try_build_grobid_returns_none_when_url_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin GROBID_URL configurado, _try_build_grobid retorna None sin probar conexión."""
    from guia.container import GUIAContainer

    # Construir solo lo necesario sin invocar el __init__ completo
    container = GUIAContainer.__new__(GUIAContainer)
    container.settings = GUIASettings(_env_file=None, grobid_url="")

    result = container._try_build_grobid()
    assert result is None


def test_try_build_grobid_returns_none_when_service_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si GROBID_URL está pero el servicio no responde, retorna None (degraded mode)."""
    from guia.container import GUIAContainer

    container = GUIAContainer.__new__(GUIAContainer)
    container.settings = GUIASettings(
        _env_file=None, grobid_url="http://nope:9999"
    )

    # Mock httpx para simular servicio caído
    import httpx

    def fake_get(url: str, timeout: float = 0) -> object:
        raise httpx.ConnectError("no reachable")

    monkeypatch.setattr(httpx, "get", fake_get)
    result = container._try_build_grobid()
    assert result is None


def test_try_build_grobid_returns_client_when_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si GROBID responde 200 a /api/isalive, retorna el cliente."""
    from guia.container import GUIAContainer
    from guia.grobid import GrobidClient

    container = GUIAContainer.__new__(GUIAContainer)
    container.settings = GUIASettings(
        _env_file=None, grobid_url="http://grobid:8070"
    )

    class FakeResponse:
        status_code = 200

    def fake_get(url: str, timeout: float = 0) -> FakeResponse:
        return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "get", fake_get)
    result = container._try_build_grobid()
    assert isinstance(result, GrobidClient)
    assert result.base_url == "http://grobid:8070"
