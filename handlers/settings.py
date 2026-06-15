"""Настройки профиля и статистика."""

from __future__ import annotations

import logging
from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import create_user, get_operations, get_user, update_user
from utils.finance import current_month_bounds, load_user_summary
from utils.formatting import fmt_month_title

logger = logging.getLogger(__name__)
router = Router()


class SettingsStates(StatesGroup):
    editing_field = State()


EDITABLE_FIELDS = {
    "full_name": ("ФИО", "Введите ФИО (Иванов Иван Иванович):"),
    "inn": ("ИНН", "Введите ИНН (10 или 12 цифр):"),
    "tax_rate": ("Ставка налога (%)", "Ставка: 4 (физлица) или 6 (юрлица):"),
    "base_currency": ("Основная валюта", "Код валюты: RUB, USD, EUR..."),
    "bank_account": ("Банковские реквизиты", "Введите номер счёта / реквизиты:"),
    "timezone": ("Часовой пояс", "Например: Europe/Moscow"),
}


def _settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"✏️ {label}", callback_data=f"settings_edit:{field}")]
            for field, (label, _) in EDITABLE_FIELDS.items()
        ]
    )


def _profile_text(user: dict) -> str:
    return (
        "⚙️ <b>Настройки профиля</b>\n\n"
        f"👤 ФИО: {user.get('full_name') or '—'}\n"
        f"🔢 ИНН: {user.get('inn') or '—'}\n"
        f"🏛️ Налог: {user.get('tax_rate', 6.0):.0f}%\n"
        f"💰 Валюта: {user.get('base_currency', 'RUB')}\n"
        f"🏦 Реквизиты: {user.get('bank_account') or '—'}\n"
        f"🕐 Часовой пояс: {user.get('timezone', 'Europe/Moscow')}\n"
    )


@router.message(Command("settings"))
@router.message(F.text == "⚙️ Настройки")
async def cmd_settings(message: Message, db_path: str) -> None:
    user_id = message.from_user.id
    user = await get_user(db_path, user_id)
    if not user:
        await create_user(db_path, user_id, message.from_user.full_name or "")
        user = await get_user(db_path, user_id)

    await message.answer(_profile_text(user), reply_markup=_settings_keyboard())


@router.callback_query(F.data.startswith("settings_edit:"))
async def callback_settings_edit(call: CallbackQuery, state: FSMContext) -> None:
    field = call.data.split(":")[1]
    _, prompt = EDITABLE_FIELDS.get(field, ("", "Введите значение:"))
    await state.set_state(SettingsStates.editing_field)
    await state.update_data(editing_field=field)
    await call.message.answer(prompt)
    await call.answer()


@router.message(SettingsStates.editing_field)
async def handle_field_value(message: Message, state: FSMContext, db_path: str) -> None:
    data = await state.get_data()
    field = data.get("editing_field")
    if not field:
        await state.clear()
        return

    value = message.text.strip()

    if field == "tax_rate":
        try:
            value_f = float(value.replace(",", "."))
            if not 0 <= value_f <= 100:
                raise ValueError
            await update_user(db_path, message.from_user.id, tax_rate=value_f)
            value = str(value_f)
        except ValueError:
            await message.answer("❌ Число от 0 до 100.")
            return
    elif field == "inn":
        if not value.isdigit() or len(value) not in (10, 12):
            await message.answer("❌ ИНН: 10 или 12 цифр.")
            return
        await update_user(db_path, message.from_user.id, inn=value)
    elif field == "base_currency":
        value = value.upper()
        if len(value) < 3:
            await message.answer("❌ Пример: RUB, USD, EUR.")
            return
        await update_user(db_path, message.from_user.id, base_currency=value)
    else:
        await update_user(db_path, message.from_user.id, **{field: value})

    await state.clear()
    label = EDITABLE_FIELDS[field][0]
    await message.answer(f"✅ <b>{label}</b>: <code>{value}</code>")


@router.message(Command("stats"))
@router.message(F.text == "📈 Статистика")
async def cmd_stats(message: Message, db_path: str) -> None:
    user_id = message.from_user.id
    today = date.today()
    date_from, date_to = current_month_bounds()

    user, summary, base_currency = await load_user_summary(
        db_path, user_id, date_from, date_to
    )
    tax_rate = user.get("tax_rate", 6.0) if user else 6.0

    top_cats = sorted(
        summary.expense_by_category.items(), key=lambda x: x[1], reverse=True
    )[:3]
    top_str = "\n".join(
        f"  • {cat}: {amt:,.0f} {base_currency}" for cat, amt in top_cats
    ) or "  Нет расходов"

    await message.answer(
        f"📈 <b>Статистика за {fmt_month_title(today)}</b>\n\n"
        f"💰 Доходы:  <b>{summary.total_income:,.2f} {base_currency}</b>\n"
        f"💸 Расходы: <b>{summary.total_expense:,.2f} {base_currency}</b>\n"
        f"📊 Прибыль: <b>{summary.net:,.2f} {base_currency}</b>\n"
        f"🏛️ Налог ~{tax_rate:.0f}%: <b>{summary.tax:,.2f} {base_currency}</b>\n"
        f"📝 Операций: {summary.operation_count}\n\n"
        f"🔝 Топ расходов:\n{top_str}"
    )
