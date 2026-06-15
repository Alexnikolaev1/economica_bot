"""Управление интеграцией Google Sheets."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import Config
from database import delete_sheets_config, get_sheets_config, upsert_sheets_config
from services.sheets_service import (
    extract_spreadsheet_id,
    get_service_account_email,
    sync_all_operations,
    verify_spreadsheet_access,
)

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("sheets"))
async def cmd_sheets(message: Message, db_path: str, config: Config) -> None:
    """
    /sheets — статус
    /sheets link <ID или URL> — привязать таблицу
    /sheets sync — полная синхронизация
    /sheets unlink — отвязать
    """
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=2)
    action = parts[1].lower() if len(parts) > 1 else "status"

    if not config.sheets_enabled:
        await message.answer(
            "📊 Google Sheets не настроен на сервере.\n"
            "Администратору нужно задать <code>GOOGLE_SHEETS_CREDENTIALS_JSON</code>."
        )
        return

    sa_email = get_service_account_email(config.google_sheets_credentials_json)

    if action == "link":
        if len(parts) < 3:
            await message.answer(
                "📎 Формат: <code>/sheets link ID_таблицы</code>\n"
                "или <code>/sheets link https://docs.google.com/spreadsheets/d/...</code>\n\n"
                + (f"Дайте доступ сервисному аккаунту:\n<code>{sa_email}</code>" if sa_email else "")
            )
            return

        spreadsheet_id = extract_spreadsheet_id(parts[2])
        if not spreadsheet_id:
            await message.answer("❌ Не удалось распознать ID таблицы.")
            return

        ok, msg = await verify_spreadsheet_access(config, spreadsheet_id)
        if not ok:
            await message.answer(f"❌ {msg}")
            return

        await upsert_sheets_config(db_path, user_id, spreadsheet_id)
        _, sync_msg = await sync_all_operations(config, db_path, user_id)
        await message.answer(
            f"✅ Таблица привязана!\n"
            f"ID: <code>{spreadsheet_id}</code>\n"
            f"Лист: <b>FREELABOT</b>\n\n"
            f"{sync_msg}"
        )
        return

    if action == "sync":
        await message.answer("🔄 Синхронизирую с Google Sheets...")
        _, sync_msg = await sync_all_operations(config, db_path, user_id)
        icon = "✅" if "Ошибка" not in sync_msg else "❌"
        await message.answer(f"{icon} {sync_msg}")
        return

    if action == "unlink":
        if await delete_sheets_config(db_path, user_id):
            await message.answer("✅ Таблица отвязана.")
        else:
            await message.answer("Таблица не была привязана.")
        return

    sheets_cfg = await get_sheets_config(db_path, user_id)
    if sheets_cfg:
        status = (
            "📊 <b>Google Sheets</b>\n\n"
            f"✅ Привязана\n"
            f"ID: <code>{sheets_cfg['spreadsheet_id']}</code>\n"
            f"Лист: {sheets_cfg.get('sheet_name', 'FREELABOT')}\n\n"
            "Команды:\n"
            "/sheets sync — полная синхронизация\n"
            "/sheets unlink — отвязать"
        )
    else:
        status = (
            "📊 <b>Google Sheets</b>\n\n"
            "❌ Таблица не привязана\n\n"
            "1. Создайте Google Таблицу\n"
            + (f"2. Дайте доступ: <code>{sa_email}</code>\n" if sa_email else "")
            + "3. <code>/sheets link ID_или_URL</code>\n\n"
            "Новые операции синхронизируются автоматически."
        )
    await message.answer(status)
