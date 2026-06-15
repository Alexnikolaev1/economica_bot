"""
Middleware — внедрение конфигурации в хендлеры через data-dict aiogram.
"""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from config import Config


class ConfigMiddleware(BaseMiddleware):
    """Прокидывает db_path и API-ключи в каждый хендлер."""

    def __init__(self, config: Config) -> None:
        self.config = config

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["config"] = self.config
        data["db_path"] = self.config.db_path
        data["gemini_api_key"] = self.config.gemini_api_key
        data["groq_api_key"] = self.config.groq_api_key
        return await handler(event, data)
