"""Обработка финансовых операций: текст, голос, фото."""

from __future__ import annotations

import logging
from datetime import date

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from database import create_user, get_last_operations, get_user, save_operation
from services.currency_service import convert_to_base
from services.gemini_service import parse_receipt_image, parse_transaction_text
from services.groq_service import transcribe_audio
from services.sheets_service import append_operation
from utils.constants import CATEGORY_EMOJI, TYPE_LABEL
from utils.filters import FreeTextOperationFilter
from utils.formatting import fmt_amount

logger = logging.getLogger(__name__)
router = Router()


class OperationStates(StatesGroup):
    waiting_income_amount = State()
    waiting_expense_amount = State()


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Верно", callback_data="confirm_op"),
                InlineKeyboardButton(text="✏️ Изменить", callback_data="cancel_op"),
            ]
        ]
    )


def _op_summary(op: dict, base_amount: float, base_currency: str = "RUB") -> str:
    cat = op.get("category", "Другое")
    emoji = CATEGORY_EMOJI.get(cat, "📌")
    lines = [
        f"<b>{TYPE_LABEL.get(op.get('type', ''), 'Операция')}</b>",
        f"💵 Сумма: {fmt_amount(float(op.get('amount', 0)), op.get('currency', 'RUB'))}",
    ]
    if op.get("currency", "RUB") != base_currency:
        lines.append(f"🔁 В {base_currency}: {fmt_amount(base_amount, base_currency)}")
    if op.get("counterparty"):
        lines.append(f"🏢 Контрагент: {op['counterparty']}")
    lines.append(f"{emoji} Категория: {cat}")
    if op.get("description"):
        lines.append(f"📝 {op['description']}")
    if op.get("date"):
        lines.append(f"📅 {op['date']}")
    return "\n".join(lines)


async def _process_parsed_op(
    message: Message,
    parsed: dict,
    db_path: str,
    state: FSMContext,
    force_type: str | None = None,
) -> None:
    if "error" in parsed:
        errors = {
            "rate_limit": "⏳ Слишком много запросов. Подождите минуту.",
            "unclear": (
                "🤔 Не распознал операцию. Пример:\n"
                "<i>получил 15000 от ООО Вектор за лендинг</i>"
            ),
        }
        await message.answer(
            errors.get(parsed["error"], "😕 Не удалось разобрать операцию."),
            parse_mode="HTML" if parsed["error"] == "unclear" else None,
        )
        return

    if force_type:
        parsed["type"] = force_type

    user_id = message.from_user.id
    user = await get_user(db_path, user_id)
    if not user:
        await create_user(db_path, user_id)
        user = await get_user(db_path, user_id)

    base_currency = (user or {}).get("base_currency", "RUB")
    currency = parsed.get("currency", "RUB")
    amount = float(parsed.get("amount", 0))

    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше нуля.")
        return

    try:
        base_amount = await convert_to_base(db_path, amount, currency, base_currency)
    except Exception as exc:
        logger.warning("Конвертация %s→%s: %s", currency, base_currency, exc)
        base_amount = amount

    op_data = {
        "user_id": user_id,
        "type": parsed.get("type", "expense"),
        "amount_original": amount,
        "currency_original": currency,
        "amount_base": base_amount,
        "category": parsed.get("category", "Другое"),
        "description": parsed.get("description", ""),
        "counterparty": parsed.get("counterparty", ""),
        "date": parsed.get("date") or date.today().isoformat(),
    }
    await state.update_data(pending_op=op_data)

    await message.answer(
        f"Распознал операцию:\n\n{_op_summary(parsed, base_amount, base_currency)}\n\nВсё верно?",
        reply_markup=_confirm_keyboard(),
    )


@router.message(F.text == "💰 Доход")
async def btn_income(message: Message, state: FSMContext) -> None:
    await state.set_state(OperationStates.waiting_income_amount)
    await message.answer(
        "💰 Введите доход.\nПример: <i>15000 от ООО Вектор за лендинг</i>",
        parse_mode="HTML",
    )


@router.message(F.text == "💸 Расход")
async def btn_expense(message: Message, state: FSMContext) -> None:
    await state.set_state(OperationStates.waiting_expense_amount)
    await message.answer(
        "💸 Введите расход.\nПример: <i>2000 за интернет</i>",
        parse_mode="HTML",
    )


@router.message(OperationStates.waiting_income_amount, F.text)
async def handle_forced_income(
    message: Message, state: FSMContext, db_path: str, gemini_api_key: str
) -> None:
    await state.clear()
    parsed = await parse_transaction_text(gemini_api_key, message.text, message.from_user.id)
    await _process_parsed_op(message, parsed, db_path, state, force_type="income")


@router.message(OperationStates.waiting_expense_amount, F.text)
async def handle_forced_expense(
    message: Message, state: FSMContext, db_path: str, gemini_api_key: str
) -> None:
    await state.clear()
    parsed = await parse_transaction_text(gemini_api_key, message.text, message.from_user.id)
    await _process_parsed_op(message, parsed, db_path, state, force_type="expense")


@router.message(FreeTextOperationFilter())
async def handle_free_text(
    message: Message, state: FSMContext, db_path: str, gemini_api_key: str
) -> None:
    await message.answer("🔍 Анализирую...")
    parsed = await parse_transaction_text(gemini_api_key, message.text, message.from_user.id)
    await _process_parsed_op(message, parsed, db_path, state)


@router.message(StateFilter(None), F.voice)
async def handle_voice(
    message: Message,
    bot: Bot,
    state: FSMContext,
    db_path: str,
    gemini_api_key: str,
    groq_api_key: str,
) -> None:
    await message.answer("🎙️ Распознаю голос...")
    file_info = await bot.get_file(message.voice.file_id)
    audio_data = (await bot.download_file(file_info.file_path)).read()

    transcript = await transcribe_audio(groq_api_key, audio_data)
    if not transcript:
        await message.answer("😕 Не удалось распознать голос. Напишите текстом.")
        return

    await message.answer(f"📝 <i>{transcript}</i>", parse_mode="HTML")
    parsed = await parse_transaction_text(gemini_api_key, transcript, message.from_user.id)
    await _process_parsed_op(message, parsed, db_path, state)


async def _handle_image(
    message: Message,
    bot: Bot,
    state: FSMContext,
    db_path: str,
    gemini_api_key: str,
    file_id: str,
    mime_type: str,
) -> None:
    await message.answer("🧾 Анализирую чек...")
    file_info = await bot.get_file(file_id)
    image_data = (await bot.download_file(file_info.file_path)).read()
    parsed = await parse_receipt_image(gemini_api_key, image_data, mime_type, message.from_user.id)
    await _process_parsed_op(message, parsed, db_path, state)


@router.message(StateFilter(None), F.photo)
async def handle_photo(
    message: Message, bot: Bot, state: FSMContext, db_path: str, gemini_api_key: str
) -> None:
    photo = message.photo[-1]
    await _handle_image(message, bot, state, db_path, gemini_api_key, photo.file_id, "image/jpeg")


@router.message(StateFilter(None), F.document)
async def handle_document(
    message: Message, bot: Bot, state: FSMContext, db_path: str, gemini_api_key: str
) -> None:
    doc = message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await message.answer("📎 Принимаю только изображения чеков.")
        return
    await _handle_image(message, bot, state, db_path, gemini_api_key, doc.file_id, doc.mime_type)


@router.callback_query(F.data == "confirm_op")
async def callback_confirm_op(
    call: CallbackQuery, state: FSMContext, db_path: str, config: Config
) -> None:
    data = await state.get_data()
    op = data.get("pending_op")
    if not op:
        await call.answer("Операция не найдена.", show_alert=True)
        return

    try:
        op_id = await save_operation(db_path, op)
        await state.clear()
        label = "Доход" if op["type"] == "income" else "Расход"

        recent = await get_last_operations(db_path, op["user_id"], limit=1)
        full_op = recent[0] if recent else {**op, "id": op_id}
        sheets_ok = await append_operation(config, db_path, op["user_id"], full_op)
        suffix = "\n📊 → Google Sheets" if sheets_ok else ""

        await call.message.edit_text(f"✅ {label} записан! ID: #{op_id}{suffix}")
        await call.answer("Сохранено!")
    except Exception:
        logger.exception("save_operation")
        await call.answer("Ошибка сохранения.", show_alert=True)


@router.callback_query(F.data == "cancel_op")
async def callback_cancel_op(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text("✏️ Отменено. Введите операцию заново.")
    await call.answer()
