"""Генерация PDF-счетов."""

from __future__ import annotations

import logging
import re
from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, Message

from database import get_user, increment_invoice_counter
from services.pdf_service import create_invoice_pdf

logger = logging.getLogger(__name__)
router = Router()


class InvoiceStates(StatesGroup):
    waiting_amount = State()
    waiting_client = State()
    waiting_description = State()


def _parse_invoice_args(text: str) -> tuple[float, str, str] | None:
    pattern = r'/invoice\s+([\d.,]+)\s+"([^"]+)"\s+"([^"]+)"'
    m = re.match(pattern, text.strip(), re.IGNORECASE)
    if m:
        try:
            return float(m.group(1).replace(",", ".")), m.group(2), m.group(3)
        except ValueError:
            return None

    parts = text.split(maxsplit=3)
    if len(parts) >= 3:
        try:
            return (
                float(parts[1].replace(",", ".")),
                parts[2] if len(parts) > 2 else "—",
                parts[3] if len(parts) > 3 else "Оказание услуг",
            )
        except ValueError:
            return None
    return None


async def _send_invoice(
    message: Message, db_path: str, amount: float, client_name: str, description: str
) -> None:
    user_id = message.from_user.id
    user = await get_user(db_path, user_id)

    if not user:
        await message.answer("⚠️ Введите /start для регистрации.")
        return
    if not user.get("full_name") or not user.get("inn"):
        await message.answer("📋 Заполните ФИО и ИНН в /settings.")
        return

    await message.answer("📄 Генерирую счёт...")
    invoice_number = await increment_invoice_counter(db_path, user_id)

    try:
        pdf_bytes, filename = await create_invoice_pdf(
            user=user,
            client_name=client_name,
            service_description=description,
            amount=amount,
            invoice_number=invoice_number,
        )
    except Exception:
        logger.exception("PDF generation")
        await message.answer("😕 Ошибка генерации PDF.")
        return

    await message.answer_document(
        BufferedInputFile(pdf_bytes, filename=filename),
        caption=(
            f"📄 Счёт №{invoice_number} от {date.today().strftime('%d.%m.%Y')}\n"
            f"🏢 {client_name}\n💰 {amount:,.2f} руб."
        ),
    )


@router.message(Command("invoice"))
async def cmd_invoice(message: Message, state: FSMContext, db_path: str) -> None:
    args = _parse_invoice_args(message.text)
    if args:
        amount, client, desc = args
        await _send_invoice(message, db_path, amount, client, desc)
    else:
        await state.set_state(InvoiceStates.waiting_amount)
        await message.answer("📄 <b>Создание счёта</b>\n\nВведите сумму (руб.):")


@router.message(F.text == "📄 Счёт")
async def btn_invoice(message: Message, state: FSMContext) -> None:
    await state.set_state(InvoiceStates.waiting_amount)
    await message.answer("📄 <b>Счёт на оплату</b>\n\nВведите сумму (руб.):")


@router.message(InvoiceStates.waiting_amount)
async def invoice_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = float(message.text.strip().replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Корректная сумма, например: 15000")
        return
    await state.update_data(invoice_amount=amount)
    await state.set_state(InvoiceStates.waiting_client)
    await message.answer("🏢 Название заказчика:")


@router.message(InvoiceStates.waiting_client)
async def invoice_client(message: Message, state: FSMContext) -> None:
    client = message.text.strip()
    if not client:
        await message.answer("❌ Название не может быть пустым.")
        return
    await state.update_data(invoice_client=client)
    await state.set_state(InvoiceStates.waiting_description)
    await message.answer("📝 Описание работ/услуг:")


@router.message(InvoiceStates.waiting_description)
async def invoice_description(message: Message, state: FSMContext, db_path: str) -> None:
    description = message.text.strip()
    if not description:
        await message.answer("❌ Описание не может быть пустым.")
        return
    data = await state.get_data()
    await state.clear()
    await _send_invoice(
        message,
        db_path,
        data.get("invoice_amount", 0),
        data.get("invoice_client", "—"),
        description,
    )
