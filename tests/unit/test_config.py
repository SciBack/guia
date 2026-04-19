"""Tests de GUIASettings — verifica que .env.example parsea correctamente."""

from __future__ import annotations

import os

import pytest

from guia.config import GUIASettings, LLMMode


def test_default_settings_without_env() -> None:
    """GUIASettings carga defaults sin ninguna variable de entorno."""
    # Limpiar variables que puedan interferir
    env_vars = [
        "GUIA_LLM_MODE", "ENVIRONMENT", "GUIA_BASE_URL",
        "LOG_LEVEL", "REDIS_URL", "SEMANTIC_CACHE_TTL",
        "SEMANTIC_CACHE_THRESHOLD", "HARVEST_CRON",
    ]
    original = {k: os.environ.pop(k, None) for k in env_vars}

    try:
        settings = GUIASettings()
        assert settings.guia_llm_mode == LLMMode.HYBRID
        assert settings.environment == "development"
        assert settings.redis_url == "redis://localhost:6379/0"
        assert settings.semantic_cache_ttl == 3600
        assert 0.0 < settings.semantic_cache_threshold < 1.0
    finally:
        for k, v in original.items():
            if v is not None:
                os.environ[k] = v


def test_llm_mode_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """GUIA_LLM_MODE se lee correctamente del entorno."""
    monkeypatch.setenv("GUIA_LLM_MODE", "CLOUD")
    settings = GUIASettings()
    assert settings.guia_llm_mode == LLMMode.CLOUD


def test_llm_mode_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """GUIA_LLM_MODE=LOCAL se parsea correctamente."""
    monkeypatch.setenv("GUIA_LLM_MODE", "LOCAL")
    settings = GUIASettings()
    assert settings.guia_llm_mode == LLMMode.LOCAL


def test_environment_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """ENVIRONMENT se lee del entorno."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    settings = GUIASettings()
    assert settings.environment == "production"


def test_redis_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """REDIS_URL se lee del entorno."""
    monkeypatch.setenv("REDIS_URL", "redis://myhost:6380/1")
    settings = GUIASettings()
    assert settings.redis_url == "redis://myhost:6380/1"


def test_semantic_cache_threshold_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """SEMANTIC_CACHE_THRESHOLD se lee del entorno como float."""
    monkeypatch.setenv("SEMANTIC_CACHE_THRESHOLD", "0.85")
    settings = GUIASettings()
    assert settings.semantic_cache_threshold == pytest.approx(0.85)


def test_harvest_cron_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """HARVEST_CRON se lee del entorno."""
    monkeypatch.setenv("HARVEST_CRON", "30 3 * * *")
    settings = GUIASettings()
    assert settings.harvest_cron == "30 3 * * *"
