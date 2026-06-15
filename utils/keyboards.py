"""Общие клавиатуры Telegram."""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="💰 Доход"),
                KeyboardButton(text="💸 Расход"),
            ],
            [
                KeyboardButton(text="📊 Отчёт"),
                KeyboardButton(text="📄 Счёт"),
            ],
            [
                KeyboardButton(text="📋 История"),
                KeyboardButton(text="📈 Статистика"),
            ],
            [
                KeyboardButton(text="⚙️ Настройки"),
            ],
        ],
        resize_keyboard=True,
        persistent=True,
    )
