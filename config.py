"""
config.py — централизованная конфигурация бота FREELABOT.
Все чувствительные данные берутся из переменных окружения.
"""

import os
from dataclasses import dataclass


@dataclass
class Config:
    # ─── Telegram ───────────────────────────────────────────────
    bot_token: str
    webhook_url: str | None      # None → polling-режим
    port: int                    # порт веб-сервера (Railway задаёт PORT)

    # ─── AI-сервисы ─────────────────────────────────────────────
    gemini_api_key: str
    groq_api_key: str

    # ─── Google Sheets (опционально) ────────────────────────────
    google_sheets_credentials_json: str | None
    spreadsheet_id: str | None

    # ─── База данных ─────────────────────────────────────────────
    db_path: str

    # ─── Доступ ──────────────────────────────────────────────────
    allowed_user_ids: frozenset[int]  # пусто → доступ для всех

    @property
    def access_restricted(self) -> bool:
        return bool(self.allowed_user_ids)

    @property
    def sheets_enabled(self) -> bool:
        """Доступна ли интеграция Google Sheets (нужен service account JSON)."""
        return bool(self.google_sheets_credentials_json)


def _resolve_webhook_url() -> str | None:
    """Собирает публичный URL для webhook (Railway / ручная настройка)."""
    explicit = os.environ.get("WEBHOOK_URL", "").strip()
    if explicit:
        url = explicit if explicit.startswith("http") else f"https://{explicit}"
        return url.rstrip("/")

    for key in ("RAILWAY_STATIC_URL", "RAILWAY_PUBLIC_DOMAIN"):
        val = os.environ.get(key, "").strip()
        if val:
            url = val if val.startswith("http") else f"https://{val}"
            return url.rstrip("/")

    return None


def _parse_allowed_user_ids(raw: str | None) -> frozenset[int]:
    """ALLOWED_USER_IDS=123,456 — только эти Telegram ID."""
    if not raw or not raw.strip():
        return frozenset()
    ids: set[int] = set()
    for part in raw.replace(" ", "").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return frozenset(ids)


def load_config() -> Config:
    """Загружает конфигурацию из переменных окружения."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        raise ValueError("GEMINI_API_KEY не задан!")

    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        raise ValueError("GROQ_API_KEY не задан!")

    # Railway: RAILWAY_PUBLIC_DOMAIN / RAILWAY_STATIC_URL / WEBHOOK_URL
    webhook_url = _resolve_webhook_url()

    port = int(os.environ.get("PORT", "8080"))

    return Config(
        bot_token=token,
        webhook_url=webhook_url,
        port=port,
        gemini_api_key=gemini_key,
        groq_api_key=groq_key,
        google_sheets_credentials_json=os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON"),
        spreadsheet_id=os.environ.get("SPREADSHEET_ID"),
        db_path=os.environ.get("DB_PATH", "local.db"),
        allowed_user_ids=_parse_allowed_user_ids(os.environ.get("ALLOWED_USER_IDS")),
    )
