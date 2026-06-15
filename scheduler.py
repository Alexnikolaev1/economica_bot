"""Планировщик напоминаний."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from aiogram import Bot

from database import get_active_reminders

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 3600  # раз в час


async def reminder_loop(bot: Bot, db_path: str) -> None:
    """Проверяет напоминания и отправляет уведомления."""
    last_sent_day: int | None = None

    while True:
        try:
            today = date.today()
            if today.day != last_sent_day:
                reminders = await get_active_reminders(db_path, today.day)
                for rem in reminders:
                    try:
                        await bot.send_message(
                            rem["user_id"],
                            f"🔔 <b>Напоминание</b>\n\n{rem['message']}",
                        )
                    except Exception as exc:
                        logger.warning(
                            "Не удалось отправить напоминание %s: %s",
                            rem.get("id"),
                            exc,
                        )
                if reminders:
                    last_sent_day = today.day
                    logger.info("Отправлено %d напоминаний", len(reminders))
        except Exception:
            logger.exception("Ошибка в reminder_loop")

        await asyncio.sleep(CHECK_INTERVAL)
