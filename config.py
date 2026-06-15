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

    @property
    def sheets_enabled(self) -> bool:
        """Доступна ли интеграция Google Sheets (нужен service account JSON)."""
        return bool(self.google_sheets_credentials_json)


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

    # Railway автоматически задаёт RAILWAY_STATIC_URL или WEBHOOK_URL
    webhook_url = (
        os.environ.get("WEBHOOK_URL")
        or os.environ.get("RAILWAY_STATIC_URL")
    )

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
    )
