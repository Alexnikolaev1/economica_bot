"""Отчёты с диаграммой и советом ИИ."""

from __future__ import annotations

import io
import logging

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from services.gemini_service import analyze_finances
from utils.finance import load_user_summary, parse_period
from utils.formatting import fmt_period_label

logger = logging.getLogger(__name__)
router = Router()


def _build_pie_chart(expense_by_category: dict[str, float]) -> bytes | None:
    if not expense_by_category:
        return None

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.pie(
        list(expense_by_category.values()),
        labels=list(expense_by_category.keys()),
        autopct="%1.1f%%",
        startangle=140,
        pctdistance=0.85,
    )
    ax.set_title("Расходы по категориям", fontsize=13, pad=15)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


async def _generate_report(
    message: Message, db_path: str, gemini_api_key: str, period_arg: str | None
) -> None:
    user_id = message.from_user.id
    date_from, date_to = parse_period(period_arg)
    label = fmt_period_label(date_from, date_to)

    await message.answer(f"⏳ Формирую отчёт за <b>{label}</b>...")

    user, summary, base_currency = await load_user_summary(
        db_path, user_id, date_from, date_to
    )
    tax_rate = user.get("tax_rate", 6.0) if user else 6.0

    if summary.operation_count == 0:
        await message.answer(f"📭 За <b>{label}</b> операций нет.", parse_mode="HTML")
        return

    report_text = (
        f"📊 <b>Отчёт за {label}</b>\n\n"
        f"💰 Доходы:  <b>{summary.total_income:,.2f} {base_currency}</b>\n"
        f"💸 Расходы: <b>{summary.total_expense:,.2f} {base_currency}</b>\n"
        f"📈 Прибыль: <b>{summary.net:,.2f} {base_currency}</b>\n"
        f"🏛️ Налог ({tax_rate:.0f}%): <b>{summary.tax:,.2f} {base_currency}</b>\n"
    )
    if summary.max_expense_category:
        report_text += f"\n📌 Главная статья: <b>{summary.max_expense_category}</b>"

    await message.answer(report_text)

    if summary.expense_by_category:
        chart = _build_pie_chart(summary.expense_by_category)
        if chart:
            await message.answer_photo(
                BufferedInputFile(chart, filename="report.png"),
                caption="🍩 Расходы по категориям",
            )

    try:
        advice = await analyze_finances(
            gemini_api_key,
            summary.total_income,
            summary.expense_by_category,
            user_id,
            base_currency,
        )
        if advice:
            await message.answer(f"💡 <b>Совет:</b>\n{advice}")
    except Exception as exc:
        logger.warning("Gemini advice: %s", exc)


@router.message(Command("report"))
async def cmd_report(message: Message, db_path: str, gemini_api_key: str) -> None:
    args = message.text.split(maxsplit=1)
    period = args[1].strip() if len(args) > 1 else None
    await _generate_report(message, db_path, gemini_api_key, period)


@router.message(F.text == "📊 Отчёт")
async def btn_report(message: Message, db_path: str, gemini_api_key: str) -> None:
    await _generate_report(message, db_path, gemini_api_key, None)
