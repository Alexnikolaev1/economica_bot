"""Регистрация роутеров хендлеров."""

from aiogram import Router

from handlers import export as export_handler
from handlers import help as help_handler
from handlers import history as history_handler
from handlers import invoice as invoice_handler
from handlers import operations as operations_handler
from handlers import reminders as reminders_handler
from handlers import report as report_handler
from handlers import settings as settings_handler
from handlers import sheets as sheets_handler
from handlers import start as start_handler


def setup_routers() -> Router:
    root = Router()
    # Порядок важен: специфичные FSM-хендлеры до свободного текста
    root.include_router(start_handler.router)
    root.include_router(help_handler.router)
    root.include_router(settings_handler.router)
    root.include_router(invoice_handler.router)
    root.include_router(reminders_handler.router)
    root.include_router(report_handler.router)
    root.include_router(export_handler.router)
    root.include_router(sheets_handler.router)
    root.include_router(history_handler.router)
    root.include_router(operations_handler.router)
    return root
