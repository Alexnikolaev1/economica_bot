"""Экспорт операций в Excel."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from database import get_operations
from services.excel_service import build_operations_xlsx, export_filename
from utils.finance import load_user_summary, parse_period
from utils.formatting import fmt_period_label

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("export"))
async def cmd_export(message: Message, db_path: str) -> None:
    """
    /export — текущий месяц
    /export неделя — за неделю
    /export 03.2026 — за март 2026
    """
    args = message.text.split(maxsplit=1)
    period_arg = args[1].strip() if len(args) > 1 else None

    date_from, date_to = parse_period(period_arg)
    label = fmt_period_label(date_from, date_to)
    user_id = message.from_user.id

    await message.answer(f"📥 Формирую Excel за <b>{label}</b>...")

    ops = await get_operations(db_path, user_id, date_from, date_to)
    if not ops:
        await message.answer(f"📭 За <b>{label}</b> операций нет.", parse_mode="HTML")
        return

    _, summary, base_currency = await load_user_summary(
        db_path, user_id, date_from, date_to
    )

    try:
        xlsx_bytes = build_operations_xlsx(ops, base_currency, summary, label)
    except Exception:
        logger.exception("Excel export failed")
        await message.answer("😕 Не удалось создать Excel-файл.")
        return

    filename = export_filename(date_from, date_to)
    await message.answer_document(
        BufferedInputFile(xlsx_bytes, filename=filename),
        caption=(
            f"📥 Экспорт за {label}\n"
            f"Операций: {len(ops)} · Прибыль: {summary.net:,.2f} {base_currency}"
        ),
    )
