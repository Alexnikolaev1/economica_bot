"""История операций с возможностью удаления."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import delete_operation, get_last_operations
from utils.constants import CATEGORY_EMOJI, TYPE_LABEL
from utils.formatting import fmt_amount

logger = logging.getLogger(__name__)
router = Router()


def _history_keyboard(ops: list[dict]) -> InlineKeyboardMarkup | None:
    if not ops:
        return None
    buttons = [
        [InlineKeyboardButton(text=f"🗑 #{op['id']}", callback_data=f"del_op:{op['id']}")]
        for op in ops[:5]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _format_operation(op: dict, base_currency: str = "RUB") -> str:
    emoji = CATEGORY_EMOJI.get(op.get("category", "Другое"), "📌")
    type_lbl = TYPE_LABEL.get(op["type"], op["type"])
    line = (
        f"<b>#{op['id']}</b> {type_lbl} — "
        f"{fmt_amount(op['amount_base'], base_currency)}"
    )
    if op.get("counterparty"):
        line += f" ({op['counterparty']})"
    line += f"\n{emoji} {op.get('category', 'Другое')} · {op.get('date', '')}"
    if op.get("description"):
        line += f"\n📝 {op['description']}"
    return line


async def _show_history(message: Message, db_path: str) -> None:
    user_id = message.from_user.id
    ops = await get_last_operations(db_path, user_id, limit=10)

    if not ops:
        await message.answer("📭 Операций пока нет. Запишите доход или расход!")
        return

    text = "📋 <b>Последние операции</b>\n\n" + "\n\n".join(
        _format_operation(op) for op in ops
    )
    text += "\n\n<i>Нажмите 🗑 чтобы удалить операцию</i>"

    await message.answer(text, reply_markup=_history_keyboard(ops))


@router.message(Command("history"))
@router.message(F.text == "📋 История")
async def cmd_history(message: Message, db_path: str) -> None:
    await _show_history(message, db_path)


@router.callback_query(F.data.startswith("del_op:"))
async def callback_delete_op(call: CallbackQuery, db_path: str) -> None:
    op_id = int(call.data.split(":")[1])
    deleted = await delete_operation(db_path, op_id, call.from_user.id)

    if deleted:
        await call.answer("Удалено")
        await call.message.answer(f"🗑 Операция #{op_id} удалена.")
        await _show_history(call.message, db_path)
    else:
        await call.answer("Операция не найдена.", show_alert=True)
