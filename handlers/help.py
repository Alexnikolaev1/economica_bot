"""Справка /help и отмена FSM /cancel."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

router = Router()

HELP_TEXT = """
<b>📖 Справка FREELABOT</b>

<b>Операции</b> — напишите текстом, голосом или фото чека:
  <i>получил 20000 от Иванова</i>
  <i>обед 850</i>

<b>Команды:</b>
/start — главное меню
/settings — профиль и реквизиты
/stats — статистика за месяц
/report [период] — отчёт (месяц / неделя / год / 03.2026)
/export [период] — Excel-файл с операциями
/sheets — Google Таблицы (link / sync / unlink)
/history — последние 10 операций
/invoice — счёт на оплату (PDF)
/remind — налоговые напоминания
/cancel — отменить текущий ввод

<b>Кнопки меню</b> дублируют основные разделы.
""".strip()


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    await message.answer("✅ Ввод отменён. Можете продолжать работу.")
