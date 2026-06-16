"""
bot.py — точка входа FREELABOT.

Локально: polling.
Railway/production: HTTP на PORT (/health) + webhook или polling.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import load_config
from database import init_db
from handlers import setup_routers
from middlewares.auth import AuthMiddleware
from middlewares.config import ConfigMiddleware
from scheduler import reminder_loop
from services.currency_service import warmup_cache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def health_handler(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "freelabot"})


async def on_startup(bot: Bot, webhook_url: str | None) -> None:
    if webhook_url:
        await bot.set_webhook(f"{webhook_url.rstrip('/')}/webhook")
        logger.info("Webhook: %s/webhook", webhook_url)
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook не настроен — режим polling")


def create_http_app(dp: Dispatcher, bot: Bot, *, webhook: bool) -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_get("/", health_handler)

    if webhook:
        webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_handler.register(app, path="/webhook")
        setup_application(app, dp, bot=bot)

    return app


async def main() -> None:
    config = load_config()
    await init_db(config.db_path)
    await warmup_cache(config.db_path)

    if config.access_restricted:
        logger.info("Доступ ограничен: %d пользователей", len(config.allowed_user_ids))
    else:
        logger.info("ALLOWED_USER_IDS не задан — доступ открыт для всех")

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(ConfigMiddleware(config))
    dp.update.middleware(AuthMiddleware(config.allowed_user_ids))
    dp.include_router(setup_routers())

    reminder_task = asyncio.create_task(reminder_loop(bot, config.db_path))
    runner: web.AppRunner | None = None
    polling_task: asyncio.Task | None = None

    # Railway всегда задаёт PORT — поднимаем HTTP для healthcheck
    run_http = "PORT" in os.environ
    use_webhook = bool(config.webhook_url)

    try:
        await on_startup(bot, config.webhook_url if use_webhook else None)

        if run_http:
            app = create_http_app(dp, bot, webhook=use_webhook)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host="0.0.0.0", port=config.port)
            await site.start()
            logger.info(
                "HTTP 0.0.0.0:%d | health=ok | webhook=%s",
                config.port,
                use_webhook,
            )

            if not use_webhook:
                logger.warning(
                    "Задайте WEBHOOK_URL или включите Public Networking в Railway "
                    "(нужен RAILWAY_PUBLIC_DOMAIN). Сейчас: polling + /health."
                )
                polling_task = asyncio.create_task(dp.start_polling(bot))

            await asyncio.Event().wait()
        else:
            await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        if polling_task:
            polling_task.cancel()
        for task in (reminder_task, polling_task):
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if runner:
            await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
