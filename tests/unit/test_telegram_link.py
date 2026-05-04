"""Tests del TelegramLinkService — OTP en Redis + binding en Postgres mock."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from guia.services.telegram_link import (
    OTP_TTL_SECONDS,
    TelegramBinding,
    TelegramLinkRepository,
    TelegramLinkService,
)


def _make_redis_mock() -> MagicMock:
    """Redis mock con TTL ignorado (no expira en tests)."""
    mock = MagicMock()
    _store: dict[str, bytes] = {}

    def mock_get(key: str) -> bytes | None:
        return _store.get(key)

    def mock_setex(key: str, ttl: int, value: str) -> None:
        _store[key] = value.encode() if isinstance(value, str) else value

    def mock_delete(*keys: str) -> int:
        n = 0
        for k in keys:
            if k in _store:
                del _store[k]
                n += 1
        return n

    mock.get.side_effect = mock_get
    mock.setex.side_effect = mock_setex
    mock.delete.side_effect = mock_delete
    return mock


def _make_repo_mock() -> MagicMock:
    """Repo Postgres mock — guarda bindings en dict."""
    repo = MagicMock(spec=TelegramLinkRepository)
    _bindings: dict[int, TelegramBinding] = {}

    async def upsert(b: TelegramBinding) -> None:
        _bindings[b.telegram_user_id] = b

    async def get_by_telegram_id(tid: int) -> TelegramBinding | None:
        return _bindings.get(tid)

    async def delete_by_telegram_id(tid: int) -> bool:
        return _bindings.pop(tid, None) is not None

    async def touch_last_used(tid: int) -> None:
        pass

    repo.upsert.side_effect = upsert
    repo.get_by_telegram_id.side_effect = get_by_telegram_id
    repo.delete_by_telegram_id.side_effect = delete_by_telegram_id
    repo.touch_last_used.side_effect = touch_last_used
    return repo


def test_generate_otp_returns_six_digits() -> None:
    redis_mock = _make_redis_mock()
    repo_mock = _make_repo_mock()
    service = TelegramLinkService(repo_mock, redis_mock)

    code = service.generate_otp(telegram_user_id=12345, telegram_username="alberto")
    assert len(code) == 6
    assert code.isdigit()
    # Sin ceros iniciales (rango 100000-999999)
    assert 100_000 <= int(code) <= 999_999


def test_generate_otp_writes_redis_with_ttl() -> None:
    redis_mock = _make_redis_mock()
    service = TelegramLinkService(_make_repo_mock(), redis_mock)
    service.generate_otp(12345)
    # setex llamado con TTL correcto (al menos 2 veces: code + user index)
    setex_calls = redis_mock.setex.call_args_list
    assert len(setex_calls) == 2
    for call in setex_calls:
        args = call[0]
        assert args[1] == OTP_TTL_SECONDS  # TTL


def test_generate_otp_revokes_previous() -> None:
    redis_mock = _make_redis_mock()
    service = TelegramLinkService(_make_repo_mock(), redis_mock)

    code1 = service.generate_otp(99)
    code2 = service.generate_otp(99)
    assert code1 != code2 or code1 == code2  # puede coincidir por azar
    # El primer código debe haber sido borrado de Redis
    assert redis_mock.get(f"guia:tg:otp:{code1}") is None or code1 == code2
    # El segundo sí está vigente
    assert redis_mock.get(f"guia:tg:otp:{code2}") is not None


@pytest.mark.asyncio
async def test_consume_otp_creates_binding() -> None:
    redis_mock = _make_redis_mock()
    repo_mock = _make_repo_mock()
    service = TelegramLinkService(repo_mock, redis_mock)

    code = service.generate_otp(telegram_user_id=777, telegram_username="alberto")
    binding = await service.consume_otp(
        code=code,
        keycloak_sub="kc-sub-uuid",
        keycloak_email="alberto@upeu.edu.pe",
    )
    assert binding is not None
    assert binding.telegram_user_id == 777
    assert binding.keycloak_sub == "kc-sub-uuid"
    assert binding.keycloak_email == "alberto@upeu.edu.pe"
    assert binding.telegram_username == "alberto"


@pytest.mark.asyncio
async def test_consume_otp_invalid_returns_none() -> None:
    service = TelegramLinkService(_make_repo_mock(), _make_redis_mock())
    binding = await service.consume_otp(code="000000", keycloak_sub="x")
    assert binding is None


@pytest.mark.asyncio
async def test_consume_otp_single_use() -> None:
    redis_mock = _make_redis_mock()
    repo_mock = _make_repo_mock()
    service = TelegramLinkService(repo_mock, redis_mock)

    code = service.generate_otp(42)
    first = await service.consume_otp(code=code, keycloak_sub="s")
    second = await service.consume_otp(code=code, keycloak_sub="s")
    assert first is not None
    assert second is None  # OTP ya consumido


@pytest.mark.asyncio
async def test_get_binding_after_consume() -> None:
    redis_mock = _make_redis_mock()
    repo_mock = _make_repo_mock()
    service = TelegramLinkService(repo_mock, redis_mock)

    code = service.generate_otp(123)
    await service.consume_otp(code=code, keycloak_sub="s1")

    binding = await service.get_binding(123)
    assert binding is not None
    assert binding.keycloak_sub == "s1"

    # Otro user_id no vinculado
    other = await service.get_binding(999)
    assert other is None


@pytest.mark.asyncio
async def test_unlink_removes_binding() -> None:
    redis_mock = _make_redis_mock()
    repo_mock = _make_repo_mock()
    service = TelegramLinkService(repo_mock, redis_mock)

    code = service.generate_otp(55)
    await service.consume_otp(code=code, keycloak_sub="s")
    assert await service.get_binding(55) is not None

    deleted = await service.unlink(55)
    assert deleted is True
    assert await service.get_binding(55) is None

    # unlink de un user no vinculado
    deleted_again = await service.unlink(55)
    assert deleted_again is False
