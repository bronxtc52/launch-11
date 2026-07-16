"""Entrypoint: Sentry -> config/token check -> DB migrations -> long-polling."""
from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot

from .config import Settings
from .observability import init_sentry


async def _run() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()  # raises if LAUNCH11_BOT_TOKEN / ANTHROPIC_API_KEY missing

    init_sentry(settings.sentry_dsn, release=os.environ.get("GIT_SHA"))

    import asyncpg

    from .db.pg_repo import PgRepo, apply_migrations
    from .tg.bot import build_dispatcher

    pool = await asyncpg.create_pool(settings.database_url)
    await apply_migrations(pool)
    repo = PgRepo(pool)

    bot = Bot(token=settings.launch11_bot_token.get_secret_value())
    dp = build_dispatcher(settings, repo)
    # /skip existed but was invisible — a human stuck on a question had no way to learn it
    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать / продолжить"),
        BotCommand(command="skip", description="Пропустить текущий вопрос"),
        BotCommand(command="progress", description="Показать прогресс по шагам"),
        BotCommand(command="reset", description="Начать заново"),
    ])
    try:
        # long-polling: single consumer, no ingress (see docker-compose)
        await dp.start_polling(bot)
    finally:
        await pool.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
