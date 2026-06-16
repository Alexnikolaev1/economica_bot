"""
Middleware — доступ только для пользователей из ALLOWED_USER_IDS.
Если список пуст — доступ открыт для всех.
"""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update


class AuthMiddleware(BaseMiddleware):
    def __init__(self, allowed_user_ids: frozenset[int]) -> None:
        self.allowed_user_ids = allowed_user_ids

    def _extract_user_id(self, event: TelegramObject) -> int | None:
        if isinstance(event, Message) and event.from_user:
            return event.from_user.id
        if isinstance(event, CallbackQuery) and event.from_user:
            return event.from_user.id
        if isinstance(event, Update):
            if event.message and event.message.from_user:
                return event.message.from_user.id
            if event.callback_query and event.callback_query.from_user:
                return event.callback_query.from_user.id
        return None

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self.allowed_user_ids:
            return await handler(event, data)

        user_id = self._extract_user_id(event)
        if user_id is not None and user_id in self.allowed_user_ids:
            return await handler(event, data)

        if user_id is not None:
            text = (
                f"⛔ У вас нет доступа к этому боту.\n"
                f"Ваш Telegram ID: <code>{user_id}</code>\n\n"
                "Передайте его администратору для добавления в список."
            )
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                await event.answer("Нет доступа.", show_alert=True)
                if event.message:
                    await event.message.answer(text)
        return None
