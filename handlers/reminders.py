"""Налоговые и финансовые напоминания."""

from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import add_reminder, delete_reminder, get_user_reminders

logger = logging.getLogger(__name__)
router = Router()


def _reminders_keyboard(reminders: list[dict]) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=f"🗑 {r['day_of_month']} число",
                callback_data=f"del_rem:{r['id']}",
            )
        ]
        for r in reminders
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else InlineKeyboardMarkup(inline_keyboard=[])


@router.message(Command("remind"))
async def cmd_remind(message: Message, db_path: str) -> None:
    """
    /remind — список напоминаний
    /remind 25 Оплатить налог УСН — добавить
    """
    user_id = message.from_user.id
    payload = message.text.replace("/remind", "", 1).strip()

    if not payload:
        reminders = await get_user_reminders(db_path, user_id)
        if not reminders:
            await message.answer(
                "🔔 Напоминаний нет.\n\n"
                "Добавить: <code>/remind 25 Оплатить налог УСН</code>",
                parse_mode="HTML",
            )
            return

        lines = "\n".join(
            f"• <b>{r['day_of_month']} число</b>: {r['message']}" for r in reminders
        )
        await message.answer(
            f"🔔 <b>Ваши напоминания</b>\n\n{lines}\n\n<i>Нажмите 🗑 для удаления</i>",
            reply_markup=_reminders_keyboard(reminders),
        )
        return

    match = re.match(r"^(\d{1,2})\s+(.+)$", payload, re.DOTALL)
    if not match:
        await message.answer("❌ Формат: /remind 25 Оплатить налог")
        return

    day = int(match.group(1))
    text = match.group(2).strip()
    if not 1 <= day <= 31:
        await message.answer("❌ День месяца: от 1 до 31.")
        return
    if not text:
        await message.answer("❌ Укажите текст напоминания.")
        return

    rem_id = await add_reminder(db_path, user_id, day, text)
    await message.answer(f"✅ Напоминание #{rem_id}: каждое <b>{day}</b> число\n{text}")


@router.callback_query(F.data.startswith("del_rem:"))
async def callback_delete_reminder(call: CallbackQuery, db_path: str) -> None:
    rem_id = int(call.data.split(":")[1])
    if await delete_reminder(db_path, rem_id, call.from_user.id):
        await call.answer("Удалено")
        await call.message.edit_text("🔔 Напоминание удалено.")
    else:
        await call.answer("Не найдено.", show_alert=True)
