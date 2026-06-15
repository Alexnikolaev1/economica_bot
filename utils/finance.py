"""Финансовые утилиты: разбор периодов и агрегация."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from database import FinancialSummary, get_financial_summary, get_user


def parse_period(arg: str | None) -> tuple[str, str]:
    """
    Разбирает аргумент периода.
    Допустимо: месяц, неделя, год, MM.YYYY или пусто (текущий месяц).
    """
    today = date.today()

    if not arg or arg.lower() in ("месяц", "month"):
        first = today.replace(day=1)
        last_day = monthrange(today.year, today.month)[1]
        return first.isoformat(), today.replace(day=last_day).isoformat()

    if arg.lower() in ("неделя", "week"):
        monday = today - timedelta(days=today.weekday())
        return monday.isoformat(), today.isoformat()

    if arg.lower() in ("год", "year"):
        return today.replace(month=1, day=1).isoformat(), today.isoformat()

    parts = arg.split(".")
    if len(parts) == 2:
        try:
            month, year = int(parts[0]), int(parts[1])
            first = date(year, month, 1)
            last_day = monthrange(year, month)[1]
            return first.isoformat(), date(year, month, last_day).isoformat()
        except ValueError:
            pass

    first = today.replace(day=1)
    return first.isoformat(), today.isoformat()


def current_month_bounds() -> tuple[str, str]:
    today = date.today()
    first = today.replace(day=1).isoformat()
    last_day = monthrange(today.year, today.month)[1]
    last = today.replace(day=last_day).isoformat()
    return first, last


async def load_user_summary(
    db_path: str,
    user_id: int,
    date_from: str,
    date_to: str,
) -> tuple[dict | None, FinancialSummary, str]:
    """Возвращает (user, summary, base_currency)."""
    user = await get_user(db_path, user_id)
    tax_rate = user.get("tax_rate", 6.0) if user else 6.0
    base_currency = user.get("base_currency", "RUB") if user else "RUB"
    summary = await get_financial_summary(
        db_path, user_id, date_from, date_to, tax_rate
    )
    return user, summary, base_currency
