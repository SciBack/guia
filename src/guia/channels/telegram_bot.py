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

    # NOTA: telegram NO hace warmup de modelos (a diferencia del api).
    # Pre-cargar el embedder aquí cuesta ~2.5GB residentes permanentes en una
    # VM de 9.7GB que ya aloja opensearch+chainlit+api con sus propias copias
    # — verificado 2026-06-11: con los 4 procesos calientes el swap se saturó
    # y las queries pasaron de 5s a 62s por thrashing. Con ~0 tráfico Telegram,
    # la primera consulta paga el lazy-load (~60-90s, sin OOM gracias al lock
    # del adapter y al swap ampliado) y las siguientes van normales.

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
            "/help — Ver esta ayuda\n"
            "/vincular — Vincular tu cuenta UPeU para queries personales\n"
            "/desvincular — Desvincular tu cuenta UPeU\n"
            "/yo — Ver tu vinculación actual\n\n"
            "Sin vincular puedes hacer consultas públicas (tesis, artículos).\n"
            "Vinculado puedes consultar tus datos personales (préstamos Koha, etc.)."
        )

    @dp.message(Command("vincular"))
    async def cmd_vincular(message: Message) -> None:
        user = message.from_user
        if user is None:
            await message.answer("No puedo identificar tu cuenta de Telegram.")
            return
        # Si ya está vinculado, avisar
        existing = await container.telegram_link_service.get_binding(user.id)
        if existing is not None:
            await message.answer(
                f"Tu cuenta ya está vinculada a *{existing.keycloak_email or existing.keycloak_username or 'UPeU'}*.\n"
                "Usa /desvincular si quieres romper la vinculación.",
                parse_mode="Markdown",
            )
            return
        code = container.telegram_link_service.generate_otp(
            user.id, telegram_username=user.username
        )
        await message.answer(
            "🔗 *Código de vinculación*\n\n"
            f"`{code}`\n\n"
            "1. Abre https://guia.upeu.edu.pe e inicia sesión con tu cuenta UPeU.\n"
            "2. En el chat, escribe:\n"
            f"   `/vincular {code}`\n\n"
            f"⏱️ El código vence en 10 minutos.",
            parse_mode="Markdown",
        )

    @dp.message(Command("desvincular"))
    async def cmd_desvincular(message: Message) -> None:
        user = message.from_user
        if user is None:
            return
        existed = await container.telegram_link_service.unlink(user.id)
        if existed:
            await message.answer(
                "✅ Tu cuenta fue desvinculada. Ya no tendré acceso a tus datos personales."
            )
        else:
            await message.answer("No tenías ninguna cuenta vinculada.")

    @dp.message(Command("yo"))
    async def cmd_yo(message: Message) -> None:
        user = message.from_user
        if user is None:
            return
        binding = await container.telegram_link_service.get_binding(user.id)
        if binding is None:
            await message.answer(
                "No estás vinculado. Usa /vincular para asociar tu cuenta UPeU."
            )
            return
        email = binding.keycloak_email or binding.keycloak_username or "(sin email)"
        await message.answer(
            "📋 *Tu vinculación*\n\n"
            f"Email UPeU: `{email}`\n"
            f"Vinculado: {binding.created_at.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            "Usa /desvincular para romper la asociación.",
            parse_mode="Markdown",
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
            # Si el usuario está vinculado a Keycloak, pasamos su sub para
            # habilitar queries personales (ChatService leerá UserProfile).
            binding = await container.telegram_link_service.get_binding(user_id)
            chat_user_id = binding.keycloak_sub if binding else f"telegram:{user_id}"
            if binding is not None:
                # Best-effort: marca last_used (no bloquea respuesta)
                await container.telegram_link_service.touch(user_id)

            request = ChatRequest(
                query=message.text or "",
                user_id=chat_user_id,
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
