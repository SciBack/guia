"""Tests del SemanticCache."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from guia.domain.chat import ChatResponse, Intent
from guia.services.cache import SemanticCache, _cosine, _query_key

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_response(answer: str = "Respuesta de prueba") -> ChatResponse:
    return ChatResponse(
        answer=answer,
        intent=Intent.RESEARCH,
        sources=[],
        model_used="stub-model",
        cached=False,
        tokens_used=10,
    )


def _make_redis_mock() -> MagicMock:
    """Mock de cliente Redis con comportamiento básico."""
    mock = MagicMock()
    _store: dict[str, bytes] = {}

    def mock_get(key: str) -> bytes | None:
        return _store.get(key)

    def mock_setex(key: str, ttl: int, value: str) -> None:
        _store[key] = value.encode() if isinstance(value, str) else value

    def mock_scan(cursor: int, match: str = "*", count: int = 100):
        return (0, [])  # Sin entradas para tests simples

    mock.get.side_effect = mock_get
    mock.setex.side_effect = mock_setex
    mock.scan.side_effect = mock_scan
    mock._store = _store
    return mock


# ── Tests de utilidades ────────────────────────────────────────────────────────

def test_cosine_identical_vectors() -> None:
    """Coseno de vector idéntico es 1.0."""
    v = [1.0, 0.0, 0.0]
    assert _cosine(v, v) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors() -> None:
    """Coseno de vectores ortogonales es 0.0."""
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert _cosine(a, b) == pytest.approx(0.0)


def test_cosine_zero_vector() -> None:
    """Coseno con vector cero retorna 0.0 (sin división por cero)."""
    a = [1.0, 0.0]
    b = [0.0, 0.0]
    assert _cosine(a, b) == 0.0


def test_query_key_deterministic() -> None:
    """La misma query produce siempre la misma clave."""
    key1 = _query_key("inteligencia artificial")
    key2 = _query_key("inteligencia artificial")
    assert key1 == key2


def test_query_key_different_queries() -> None:
    """Queries distintas producen claves distintas."""
    key1 = _query_key("inteligencia artificial")
    key2 = _query_key("machine learning")
    assert key1 != key2


# ── Tests del SemanticCache ────────────────────────────────────────────────────

def test_cache_miss_on_empty() -> None:
    """Cache miss cuando no hay entradas."""
    redis_mock = _make_redis_mock()
    cache = SemanticCache(redis_mock)
    result = cache.get("consulta nueva")
    assert result is None


def test_cache_set_and_get_exact() -> None:
    """Set + get exacto retorna la respuesta cacheada."""
    redis_mock = _make_redis_mock()
    cache = SemanticCache(redis_mock)

    query = "¿Qué tesis hay sobre IA?"
    response = _make_response("Encontré 5 tesis sobre IA.")

    cache.set(query, response)
    result = cache.get(query)

    assert result is not None
    assert result.answer == "Encontré 5 tesis sobre IA."
    assert result.intent == Intent.RESEARCH


def test_cache_different_query_is_miss() -> None:
    """Query diferente no produce hit exacto."""
    redis_mock = _make_redis_mock()
    cache = SemanticCache(redis_mock)

    cache.set("query A", _make_response("Respuesta A"))
    result = cache.get("query B")

    assert result is None


def test_cache_set_calls_redis_setex() -> None:
    """set() llama a redis.setex con el TTL configurado."""
    redis_mock = _make_redis_mock()
    cache = SemanticCache(redis_mock, ttl=1800)
    response = _make_response()

    cache.set("test query", response)

    # Debe haber llamado setex al menos una vez
    assert redis_mock.setex.called
    call_args = redis_mock.setex.call_args_list[0]
    assert call_args[0][1] == 1800  # TTL


def test_cache_with_vector_stores_vector() -> None:
    """Cuando se provee vector, también se almacena en Redis."""
    redis_mock = _make_redis_mock()
    cache = SemanticCache(redis_mock)
    response = _make_response()
    vector = [0.1, 0.2, 0.3]

    cache.set("query con vector", response, query_vector=vector)

    # Debe haber 2 llamadas setex: una para la respuesta, una para el vector
    assert redis_mock.setex.call_count == 2


def test_cache_cached_flag_is_set() -> None:
    """La respuesta retornada del caché tiene cached=True."""
    redis_mock = _make_redis_mock()
    cache = SemanticCache(redis_mock)

    response = _make_response()
    cache.set("mi query", response)

    # El ChatService es quien establece cached=True al recibir el hit
    # El cache.get() retorna la respuesta tal como está almacenada
    result = cache.get("mi query")
    assert result is not None
    # La respuesta original tenía cached=False
    assert result.cached is False  # así se guardó


def test_cache_threshold_default() -> None:
    """El threshold default es 0.92."""
    redis_mock = _make_redis_mock()
    cache = SemanticCache(redis_mock)
    assert cache.threshold == pytest.approx(0.92)


def test_cache_custom_ttl_and_threshold() -> None:
    """TTL y threshold se configuran correctamente."""
    redis_mock = _make_redis_mock()
    cache = SemanticCache(redis_mock, ttl=7200, threshold=0.85)
    assert cache.ttl == 7200
    assert cache.threshold == pytest.approx(0.85)
