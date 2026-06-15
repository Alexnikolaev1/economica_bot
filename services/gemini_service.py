"""
services/gemini_service.py — Google Gemini 1.5 Flash.
"""

from __future__ import annotations

import base64
import json
import logging
import re

import aiohttp

from utils.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent"
)

CATEGORIES = [
    "Транспорт", "Питание", "Сервисы", "Налоги",
    "Оборудование", "Маркетинг", "Зарплата",
    "Личные расходы", "Другое",
]

TRANSACTION_PROMPT = """
Ты — финансовый помощник фрилансера. Извлеки из текста данные об операции.
Верни СТРОГО JSON без пояснений и markdown:
{{
  "type": "income" или "expense",
  "amount": число,
  "currency": "RUB" (или USD/EUR/GBP и т.д.),
  "category": одна из [{categories}],
  "counterparty": "название клиента или магазина" или null,
  "description": "краткое описание",
  "date": "ГГГГ-ММ-ДД" или null
}}

Если тип операции неясен — верни {{"error": "unclear"}}.

Текст: {text}
""".strip()

RECEIPT_PROMPT = """
Извлеки из чека сумму, дату, магазин и описание покупки.
Верни СТРОГО JSON:
{{
  "type": "expense",
  "amount": число,
  "currency": "RUB",
  "category": "одна из категорий",
  "counterparty": "название магазина",
  "description": "краткое описание",
  "date": "ГГГГ-ММ-ДД или null"
}}
Категории: Транспорт, Питание, Сервисы, Налоги, Оборудование, Маркетинг, Зарплата, Личные расходы, Другое.
""".strip()


async def _call_gemini(api_key: str, parts: list[dict], user_id: int) -> str | None:
    if not await rate_limiter.acquire(user_id):
        return None

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 512},
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{GEMINI_URL}?key={api_key}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    logger.error("Gemini HTTP %d: %s", resp.status, (await resp.text())[:300])
                    return None
                data = await resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return None
                parts_resp = candidates[0].get("content", {}).get("parts", [])
                return parts_resp[0].get("text", "") if parts_resp else None
    except Exception:
        logger.exception("Ошибка вызова Gemini")
        return None


async def parse_transaction_text(api_key: str, text: str, user_id: int) -> dict:
    prompt = TRANSACTION_PROMPT.format(categories=", ".join(CATEGORIES), text=text)
    raw = await _call_gemini(api_key, [{"text": prompt}], user_id)
    if raw is None:
        return {"error": "rate_limit"}
    return _parse_json_response(raw)


async def parse_receipt_image(
    api_key: str, image_bytes: bytes, mime_type: str, user_id: int
) -> dict:
    b64 = base64.b64encode(image_bytes).decode()
    parts = [
        {"text": RECEIPT_PROMPT},
        {"inlineData": {"mimeType": mime_type, "data": b64}},
    ]
    raw = await _call_gemini(api_key, parts, user_id)
    if raw is None:
        return {"error": "rate_limit"}
    return _parse_json_response(raw)


async def analyze_finances(
    api_key: str,
    income: float,
    expense_by_category: dict[str, float],
    user_id: int,
    base_currency: str = "RUB",
) -> str:
    cats_str = "; ".join(
        f"{cat}: {amt:.0f} {base_currency}"
        for cat, amt in expense_by_category.items()
    )
    prompt = (
        f"Финансы фрилансера за период:\n"
        f"Доход: {income:.0f} {base_currency}\n"
        f"Расходы: {cats_str or 'нет'}\n"
        f"Дай 3–4 предложения практического совета по оптимизации. По-русски, без вводных."
    )
    raw = await _call_gemini(api_key, [{"text": prompt}], user_id)
    return raw or "Не удалось получить аналитику. Попробуйте позже."


def _parse_json_response(raw: str) -> dict:
    clean = raw.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.MULTILINE).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        logger.error("JSON parse error. Raw: %s", raw[:300])
        return {"error": "parse_error"}
