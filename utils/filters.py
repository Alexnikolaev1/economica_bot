"""Пользовательские фильтры aiogram."""

from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from utils.constants import MENU_BUTTONS


class FreeTextOperationFilter(BaseFilter):
    """
    Пропускает только свободный текст, не являющийся командой или кнопкой меню.
    Используется для парсинга финансовых операций.
    """

    async def __call__(self, message: Message, state: FSMContext) -> bool:
        if not message.text or message.text.startswith("/"):
            return False
        if message.text in MENU_BUTTONS:
            return False
        current = await state.get_state()
        return current is None
