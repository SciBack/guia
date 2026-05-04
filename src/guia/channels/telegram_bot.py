"""Telegram bot de GUIA con aiogram v3 (Sprint 0.5).

Implementa FSM básica y rate limiting por usuario vía Redis.

Arranque:
    python -m guia.channels.telegram_bot
"""

from __future__ import annotations

import asyncio
import time

import redis
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Message

from guia.config import GUIASettings
from guia.container import GUIAContainer
from guia.domain.chat import ChatRequest
from guia.logging import configure_logging, get_logger

_settings = GUIASettings()
configure_logging(level=_settings.log_level, json_logs=True)
logger = get_logger(__name__)

# Rate limiting: ventana de 60 segundos
_RATE_WINDOW = 60
_RATE_PREFIX = "guia:tg:rate:"


class GUIAStates(StatesGroup):
    """Estados FSM del bot de Telegram."""

    waiting_for_query = State()


def _check_rate_limit(redis_client: redis.Redis, user_id: int, limit: int) -> bool:  # type: ignore[type-arg]
    """Verifica rate limit por usuario.

    Returns:
        True si el usuario está dentro del límite, False si excedió.
    """
    key = f"{_RATE_PREFIX}{user_id}"
    now = int(time.time())
    window_start = now - _RATE_WINDOW

    pipe = redis_client.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zadd(key, {str(now): now})
    pipe.zcard(key)
    pipe.expire(key, _RATE_WINDOW)
    results = pipe.execute()

    count = int(results[2])
    return count <= limit


async def main() -> None:
    """Punto de entrada del bot Telegram."""
    import os
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set — bot cannot start")
        return

    # Redis para FSM storage y rate limiting
    redis_url = _settings.redis_url
    redis_storage = RedisStorage.from_url(redis_url)
    redis_client: redis.Redis = redis.from_url(redis_url, decode_responses=True)  # type: ignore[type-arg]

    # Container GUIA
    container = GUIAContainer(_settings)

    bot = Bot(token=token)
    dp = Dispatcher(storage=redis_storage)

    @dp.message(Command("start"))
    async def cmd_start(message: Message, state: FSMContext) -> None:
        await state.set_state(GUIAStates.waiting_for_query)
        await message.answer(
            "Hola, soy GUIA, tu asistente universitario.\n"
            "Puedo ayudarte con tesis, artículos y publicaciones "
            "del repositorio institucional.\n\n"
            "Envíame tu consulta:"
        )

    @dp.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(
            "Comandos disponibles:\n"
            "/start — Iniciar conversación\n"
            "/help — Ver esta ayuda\n\n"
            "Solo envíame tu pregunta directamente."
        )

    @dp.message(F.text)
    async def handle_query(message: Message, state: FSMContext) -> None:
        user_id = message.from_user.id if message.from_user else 0

        # Rate limiting
        if not _check_rate_limit(redis_client, user_id, _settings.telegram_rate_limit):
            await message.answer(
                "Has enviado demasiadas consultas. "
                "Espera un momento antes de continuar."
            )
            return

        thinking = await message.answer("Buscando...")

        try:
            request = ChatRequest(
                query=message.text or "",
                user_id=str(user_id),
                language="es",
            )
            response = await container.chat_service.answer(request)

            answer = response.answer
            if response.sources:
                answer += "\n\nFuentes:\n"
                for i, src in enumerate(response.sources[:3], 1):
                    answer += f"{i}. {src.title}\n"
                    if src.url:
                        answer += f"   {src.url}\n"

            await thinking.edit_text(answer[:4096])  # Límite Telegram

        except Exception:
            logger.exception("telegram_handler_error")
            await thinking.edit_text(
                "Ocurrió un error procesando tu consulta. Intenta de nuevo."
            )

    logger.info("telegram_bot_starting")
    try:
        await dp.start_polling(bot)
    finally:
        await container.aclose()
        redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())
