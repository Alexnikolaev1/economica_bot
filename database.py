"""
database.py — SQLite-слой: схема, миграции, CRUD.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id          INTEGER PRIMARY KEY,
    full_name        TEXT,
    inn              TEXT,
    tax_rate         REAL    DEFAULT 6.0,
    base_currency    TEXT    DEFAULT 'RUB',
    bank_account     TEXT,
    invoice_counter  INTEGER DEFAULT 1,
    timezone         TEXT    DEFAULT 'Europe/Moscow',
    created_at       TIMESTAMP DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS operations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL,
    type              TEXT    NOT NULL CHECK(type IN ('income','expense')),
    amount_original   REAL    NOT NULL,
    currency_original TEXT    NOT NULL DEFAULT 'RUB',
    amount_base       REAL    NOT NULL,
    category          TEXT,
    description       TEXT,
    counterparty      TEXT,
    date              TEXT    DEFAULT (date('now')),
    created_at        TIMESTAMP DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS reminders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    day_of_month   INTEGER NOT NULL CHECK(day_of_month BETWEEN 1 AND 31),
    message        TEXT    NOT NULL,
    active         INTEGER DEFAULT 1,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS currency_cache (
    currency_code TEXT PRIMARY KEY,
    rate_to_base  REAL NOT NULL,
    updated_at    TIMESTAMP DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sheets_config (
    user_id        INTEGER PRIMARY KEY,
    spreadsheet_id TEXT NOT NULL,
    sheet_name     TEXT DEFAULT 'Sheet1',
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_operations_user_date ON operations(user_id, date);
CREATE INDEX IF NOT EXISTS idx_reminders_user       ON reminders(user_id, active);
"""

MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN bank_account TEXT",
]


@dataclass(frozen=True)
class FinancialSummary:
    total_income: float
    total_expense: float
    net: float
    tax: float
    operation_count: int
    expense_by_category: dict[str, float]
    max_expense_category: str


async def init_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA_SQL)
        await _run_migrations(db)
        await db.commit()
    logger.info("База данных инициализирована: %s", db_path)


async def _run_migrations(db: aiosqlite.Connection) -> None:
    for sql in MIGRATIONS:
        try:
            await db.execute(sql)
        except aiosqlite.OperationalError:
            pass  # колонка уже существует


# ─── Пользователи ────────────────────────────────────────────────────────────

async def get_user(db_path: str, user_id: int) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def create_user(db_path: str, user_id: int, full_name: str = "") -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO users (user_id, full_name, created_at)
            VALUES (?, ?, ?)
            """,
            (user_id, full_name, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def update_user(db_path: str, user_id: int, **fields: Any) -> None:
    if not fields:
        return
    allowed = {
        "full_name", "inn", "tax_rate", "base_currency",
        "bank_account", "timezone", "invoice_counter",
    }
    safe = {k: v for k, v in fields.items() if k in allowed}
    if not safe:
        return
    set_clause = ", ".join(f"{k} = ?" for k in safe)
    values = list(safe.values()) + [user_id]
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            f"UPDATE users SET {set_clause} WHERE user_id = ?", values
        )
        await db.commit()


async def increment_invoice_counter(db_path: str, user_id: int) -> int:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE users SET invoice_counter = invoice_counter + 1 WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()
        async with db.execute(
            "SELECT invoice_counter FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 1


# ─── Операции ────────────────────────────────────────────────────────────────

async def save_operation(db_path: str, op: dict) -> int:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            """
            INSERT INTO operations
                (user_id, type, amount_original, currency_original,
                 amount_base, category, description, counterparty, date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                op["user_id"],
                op["type"],
                op["amount_original"],
                op.get("currency_original", "RUB"),
                op["amount_base"],
                op.get("category", "Другое"),
                op.get("description", ""),
                op.get("counterparty", ""),
                op.get("date", date.today().isoformat()),
            ),
        ) as cur:
            new_id = cur.lastrowid
        await db.commit()
    return new_id


async def get_operations(
    db_path: str,
    user_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    query = "SELECT * FROM operations WHERE user_id = ?"
    params: list[Any] = [user_id]

    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)

    query += " ORDER BY date DESC, created_at DESC"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_last_operations(
    db_path: str, user_id: int, limit: int = 10
) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM operations
            WHERE user_id = ?
            ORDER BY date DESC, created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_operation(db_path: str, op_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "DELETE FROM operations WHERE id = ? AND user_id = ?",
            (op_id, user_id),
        ) as cur:
            deleted = cur.rowcount > 0
        await db.commit()
    return deleted


async def get_financial_summary(
    db_path: str,
    user_id: int,
    date_from: str,
    date_to: str,
    tax_rate: float,
) -> FinancialSummary:
    ops = await get_operations(db_path, user_id, date_from, date_to)

    total_income = 0.0
    total_expense = 0.0
    expense_by_category: dict[str, float] = {}

    for op in ops:
        amount = op.get("amount_base", 0.0)
        if op["type"] == "income":
            total_income += amount
        else:
            total_expense += amount
            cat = op.get("category", "Другое")
            expense_by_category[cat] = expense_by_category.get(cat, 0.0) + amount

    net = total_income - total_expense
    tax = round(total_income * tax_rate / 100, 2)
    max_cat = (
        max(expense_by_category, key=expense_by_category.__getitem__)
        if expense_by_category
        else ""
    )

    return FinancialSummary(
        total_income=total_income,
        total_expense=total_expense,
        net=net,
        tax=tax,
        operation_count=len(ops),
        expense_by_category=expense_by_category,
        max_expense_category=max_cat,
    )


# ─── Напоминания ─────────────────────────────────────────────────────────────

async def add_reminder(
    db_path: str, user_id: int, day_of_month: int, message: str
) -> int:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "INSERT INTO reminders (user_id, day_of_month, message) VALUES (?, ?, ?)",
            (user_id, day_of_month, message),
        ) as cur:
            new_id = cur.lastrowid
        await db.commit()
    return new_id


async def get_active_reminders(db_path: str, day_of_month: int) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM reminders WHERE day_of_month = ? AND active = 1",
            (day_of_month,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_user_reminders(db_path: str, user_id: int) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM reminders WHERE user_id = ? ORDER BY day_of_month",
            (user_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_reminder(db_path: str, reminder_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "DELETE FROM reminders WHERE id = ? AND user_id = ?",
            (reminder_id, user_id),
        ) as cur:
            deleted = cur.rowcount > 0
        await db.commit()
    return deleted


# ─── Кэш валют ───────────────────────────────────────────────────────────────

async def get_cached_rate(db_path: str, currency_code: str) -> float | None:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            """
            SELECT rate_to_base FROM currency_cache
            WHERE currency_code = ?
              AND updated_at > datetime('now', '-24 hours')
            """,
            (currency_code.upper(),),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def set_cached_rate(db_path: str, currency_code: str, rate: float) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO currency_cache (currency_code, rate_to_base, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(currency_code) DO UPDATE
                SET rate_to_base = excluded.rate_to_base,
                    updated_at   = excluded.updated_at
            """,
            (currency_code.upper(), rate),
        )
        await db.commit()


async def get_sheets_config(db_path: str, user_id: int) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM sheets_config WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def upsert_sheets_config(
    db_path: str,
    user_id: int,
    spreadsheet_id: str,
    sheet_name: str = "FREELABOT",
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO sheets_config (user_id, spreadsheet_id, sheet_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE
                SET spreadsheet_id = excluded.spreadsheet_id,
                    sheet_name     = excluded.sheet_name
            """,
            (user_id, spreadsheet_id, sheet_name),
        )
        await db.commit()


async def delete_sheets_config(db_path: str, user_id: int) -> bool:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "DELETE FROM sheets_config WHERE user_id = ?", (user_id,)
        ) as cur:
            deleted = cur.rowcount > 0
        await db.commit()
    return deleted
