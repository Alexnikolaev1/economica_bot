"""
services/currency_service.py — курсы валют через Frankfurter API.
"""

import logging

import aiohttp

from database import get_cached_rate, set_cached_rate

logger = logging.getLogger(__name__)

FRANKFURTER_URL = "https://api.frankfurter.app/latest"
WARMUP_CURRENCIES = ["USD", "EUR", "GBP", "CNY", "KZT", "BYN"]


async def get_rate_to_rub(db_path: str, currency_code: str) -> float:
    code = currency_code.upper()
    if code == "RUB":
        return 1.0

    cached = await get_cached_rate(db_path, code)
    if cached is not None:
        return cached

    rate = await _fetch_rate(code, "RUB")
    if rate is None:
        raise RuntimeError(f"Не удалось получить курс {code}/RUB")

    await set_cached_rate(db_path, code, rate)
    logger.info("Курс %s/RUB = %.4f", code, rate)
    return rate


async def _fetch_rate(from_currency: str, to_currency: str) -> float | None:
    params = {"from": from_currency, "to": to_currency}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                FRANKFURTER_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("rates", {}).get(to_currency)
    except Exception:
        logger.exception("Frankfurter error")
        return None


async def warmup_cache(db_path: str) -> None:
    logger.info("Прогрев кэша курсов валют...")
    for code in WARMUP_CURRENCIES:
        try:
            if await get_cached_rate(db_path, code) is None:
                rate = await _fetch_rate(code, "RUB")
                if rate:
                    await set_cached_rate(db_path, code, rate)
        except Exception as exc:
            logger.warning("Курс %s: %s", code, exc)


async def convert_to_base(
    db_path: str,
    amount: float,
    from_currency: str,
    base_currency: str = "RUB",
) -> float:
    src = from_currency.upper()
    base = base_currency.upper()
    if src == base:
        return amount

    if base == "RUB":
        return amount * await get_rate_to_rub(db_path, src)

    rate_from = await get_rate_to_rub(db_path, src)
    rate_base = await get_rate_to_rub(db_path, base)
    return amount * rate_from / rate_base
