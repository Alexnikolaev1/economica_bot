"""
bot.py — точка входа FREELABOT.

Polling локально; webhook + health на Railway/production.
"""

from __future__ import annotations

import asyncio
import logging
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
        logger.info("Режим polling")


def create_web_app(dp: Dispatcher, bot: Bot) -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health_handler)

    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path="/webhook")
    setup_application(app, dp, bot=bot)
    return app


async def main() -> None:
    config = load_config()
    await init_db(config.db_path)
    await warmup_cache(config.db_path)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(ConfigMiddleware(config))
    dp.include_router(setup_routers())

    reminder_task = asyncio.create_task(reminder_loop(bot, config.db_path))
    runner: web.AppRunner | None = None

    try:
        await on_startup(bot, config.webhook_url)

        if config.webhook_url:
            app = create_web_app(dp, bot)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host="0.0.0.0", port=config.port)
            await site.start()
            logger.info("HTTP :%d (webhook + /health)", config.port)
            await asyncio.Event().wait()
        else:
            await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        try:
            await reminder_task
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
