"""Команда /start и главное меню."""

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from database import create_user, get_user
from utils.keyboards import main_keyboard

logger = logging.getLogger(__name__)
router = Router()

WELCOME_TEXT = """
👋 Добро пожаловать в <b>FREELABOT</b> — финансовый помощник фрилансера!

<b>Возможности:</b>
• 📝 Доходы и расходы — текстом, голосом или фото чека
• 📊 Отчёты с диаграммами и советами ИИ
• 📄 PDF-счета на оплату
• 🔔 Налоговые напоминания

<b>Примеры ввода:</b>
  <i>получил 15000 от ООО Вектор за сайт</i>
  <i>такси 500р</i>

/help — все команды
""".strip()


@router.message(CommandStart())
async def cmd_start(message: Message, db_path: str) -> None:
    user_id = message.from_user.id
    full_name = message.from_user.full_name or ""

    await create_user(db_path, user_id, full_name)
    logger.info("Старт: user=%d", user_id)

    await message.answer(WELCOME_TEXT, reply_markup=main_keyboard())

    user = await get_user(db_path, user_id)
    if not user or not user.get("full_name") or not user.get("inn"):
        await message.answer(
            "📋 Профиль не заполнен. Укажите ФИО и ИНН: /settings"
        )
