"""
services/sheets_service.py — синхронизация операций с Google Sheets.

Требует service account JSON в GOOGLE_SHEETS_CREDENTIALS_JSON.
Пользователь делится таблицей с email сервисного аккаунта (client_email из JSON).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from config import Config
from database import get_operations, get_sheets_config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADERS = [
    "ID", "Дата", "Тип", "Сумма", "Валюта",
    "Сумма (база)", "Категория", "Контрагент", "Описание", "Создано",
]
TYPE_RU = {"income": "Доход", "expense": "Расход"}


def _parse_spreadsheet_id(raw: str) -> str | None:
    raw = raw.strip()
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", raw):
        return raw
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", raw)
    return match.group(1) if match else None


def get_service_account_email(credentials_json: str) -> str | None:
    try:
        return json.loads(credentials_json).get("client_email")
    except json.JSONDecodeError:
        return None


def _get_gspread_client(credentials_json: str):
    import gspread
    from google.oauth2.service_account import Credentials

    info = json.loads(credentials_json)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def _op_to_row(op: dict) -> list:
    return [
        op.get("id", ""),
        op.get("date", ""),
        TYPE_RU.get(op.get("type", ""), op.get("type", "")),
        op.get("amount_original", 0),
        op.get("currency_original", "RUB"),
        op.get("amount_base", 0),
        op.get("category", ""),
        op.get("counterparty", ""),
        op.get("description", ""),
        str(op.get("created_at", "")),
    ]


def _sync_append_operation_sync(
    credentials_json: str,
    spreadsheet_id: str,
    sheet_name: str,
    op: dict,
) -> None:
    client = _get_gspread_client(credentials_json)
    spreadsheet = client.open_by_key(spreadsheet_id)
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except Exception:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=10)

    if not worksheet.get_all_values():
        worksheet.append_row(HEADERS)

    worksheet.append_row(_op_to_row(op))


def _sync_all_operations_sync(
    credentials_json: str,
    spreadsheet_id: str,
    sheet_name: str,
    operations: list[dict],
) -> int:
    client = _get_gspread_client(credentials_json)
    spreadsheet = client.open_by_key(spreadsheet_id)
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.clear()
    except Exception:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=10)
        worksheet.clear()

    rows = [HEADERS] + [_op_to_row(op) for op in operations]
    worksheet.update(rows, "A1", value_input_option="USER_ENTERED")
    return len(operations)


def _test_access_sync(credentials_json: str, spreadsheet_id: str, sheet_name: str) -> None:
    client = _get_gspread_client(credentials_json)
    spreadsheet = client.open_by_key(spreadsheet_id)
    try:
        spreadsheet.worksheet(sheet_name)
    except Exception:
        spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=10)


async def append_operation(
    config: Config,
    db_path: str,
    user_id: int,
    op: dict,
) -> bool:
    if not config.sheets_enabled:
        return False

    sheets_cfg = await get_sheets_config(db_path, user_id)
    if not sheets_cfg:
        return False

    try:
        await asyncio.to_thread(
            _sync_append_operation_sync,
            config.google_sheets_credentials_json,
            sheets_cfg["spreadsheet_id"],
            sheets_cfg.get("sheet_name", "FREELABOT"),
            op,
        )
        return True
    except Exception:
        logger.exception("Sheets append failed for user %s", user_id)
        return False


async def sync_all_operations(config: Config, db_path: str, user_id: int) -> tuple[int, str]:
    if not config.sheets_enabled:
        return 0, "Интеграция Google Sheets не настроена администратором."

    sheets_cfg = await get_sheets_config(db_path, user_id)
    if not sheets_cfg:
        return 0, "Таблица не привязана. Используйте /sheets link <ID или URL>"

    ops = await get_operations(db_path, user_id)
    sheet_name = sheets_cfg.get("sheet_name", "FREELABOT")

    try:
        count = await asyncio.to_thread(
            _sync_all_operations_sync,
            config.google_sheets_credentials_json,
            sheets_cfg["spreadsheet_id"],
            sheet_name,
            ops,
        )
        return count, f"Синхронизировано {count} операций на лист «{sheet_name}»."
    except Exception as exc:
        logger.exception("Sheets full sync failed")
        return 0, f"Ошибка синхронизации: {exc}"


async def verify_spreadsheet_access(
    config: Config,
    spreadsheet_id: str,
    sheet_name: str = "FREELABOT",
) -> tuple[bool, str]:
    if not config.sheets_enabled:
        return False, "GOOGLE_SHEETS_CREDENTIALS_JSON не задан."

    try:
        await asyncio.to_thread(
            _test_access_sync,
            config.google_sheets_credentials_json,
            spreadsheet_id,
            sheet_name,
        )
        return True, "Доступ к таблице подтверждён."
    except Exception as exc:
        email = get_service_account_email(config.google_sheets_credentials_json)
        hint = f"\nПоделитесь таблицей с: <code>{email}</code>" if email else ""
        return False, f"Нет доступа к таблице: {exc}{hint}"


def extract_spreadsheet_id(text: str) -> str | None:
    return _parse_spreadsheet_id(text)
