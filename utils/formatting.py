"""Форматирование сумм и дат для сообщений."""

from datetime import date

from utils.constants import MONTH_NAMES_GENITIVE, MONTH_NAMES_NOMINATIVE


def fmt_amount(amount: float, currency: str = "RUB") -> str:
    return f"{amount:,.2f} {currency}"


def fmt_period_label(date_from: str, date_to: str) -> str:
    try:
        d1 = date.fromisoformat(date_from)
        d2 = date.fromisoformat(date_to)
        if d1.month == d2.month and d1.year == d2.year:
            return f"{MONTH_NAMES_NOMINATIVE[d1.month - 1]} {d1.year}"
        return f"{d1.strftime('%d.%m.%Y')} — {d2.strftime('%d.%m.%Y')}"
    except ValueError:
        return f"{date_from} — {date_to}"


def fmt_month_title(day: date) -> str:
    return f"{day.day} {MONTH_NAMES_GENITIVE[day.month - 1]} {day.year}"
