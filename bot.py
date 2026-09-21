"""
Telegram-бот расписания для группы ХТ-344.
Запуск: python3 bot.py
"""

import asyncio
import json
import os
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from dotenv import load_dotenv

# ── Загрузка конфигурации ───────────────────────────────
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("Укажите BOT_TOKEN в файле .env")

# ─── Загрузка расписания ────────────────────────────────
try:
    with open("schedule.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    SCHEDULE = data["schedule"]
    GROUP = data["group"]
    print(f"✅ Расписание загружено для группы {GROUP}")
except Exception as e:
    print(f"❌ Ошибка загрузки schedule.json: {e}")
    exit(1)

DAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
DAY_BY_NUM = {i: day for i, day in enumerate(DAYS)}

# ─── Машина состояний ───────────────────────────────────
class ScheduleStates(StatesGroup):
    waiting_for_date = State()

# ─── Инициализация бота ─────────────────────────────────
bot = Bot(token=TOKEN)
dp = Dispatcher()


# ─── Определение текущей недели ────────────────────────
def get_current_week():
    today = datetime.now()
    iso_week = today.isocalendar()[1]
    return "week1" if iso_week % 2 == 1 else "week2"


def get_week_for_date(dt: datetime):
    iso_week = dt.isocalendar()[1]
    return "week1" if iso_week % 2 == 1 else "week2"


def get_week_label(week_key: str) -> str:
    return "Нечётная неделя" if week_key == "week1" else "Чётная неделя"


def parse_date(date_str: str, year: int = None) -> datetime | None:
    if year is None:
        year = datetime.now().year
    formats = ["%d.%m", "%d.%m.%Y", "%d.%m.%y"]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if "%Y" not in fmt and "%y" not in fmt:
                dt = dt.replace(year=year)
            return dt
        except ValueError:
            continue
    return None


# ─── Форматирование ─────────────────────────────────────
def format_pair(pair_num: str, pair_data: dict) -> str:
    lines = [f" <b>{pair_num} пара</b>"]
    if pair_data.get("subject"):
        lines.append(f"   📚 {pair_data['subject']}")
    if pair_data.get("teacher"):
        lines.append(f"   👨‍ {pair_data['teacher']}")
    if pair_data.get("room"):
        lines.append(f"   🚪 Ауд. {pair_data['room']}")
    return "\n".join(lines)


def format_day(day_name: str, week_key: str) -> str:
    week_label = get_week_label(week_key)
    header = f" <b>{day_name}</b> ({week_label})\n"
    if day_name not in SCHEDULE.get(week_key, {}) or not SCHEDULE[week_key][day_name]:
        return header + "\n😴 Нет занятий"
    pairs = SCHEDULE[week_key][day_name]
    sorted_pairs = sorted(pairs.keys(), key=lambda x: int(x))
    blocks = [format_pair(p, pairs[p]) for p in sorted_pairs]
    return header + "\n" + "\n\n".join(blocks)


def format_week(week_key: str) -> str:
    week_label = get_week_label(week_key)
    lines = [f"📋 <b>Расписание на неделю — {GROUP}</b>"]
    lines.append(f"📆 <b>{week_label}</b>\n")
    for day in DAYS:
        day_text = format_day(day, week_key)
        lines.append(day_text)
        lines.append("─" * 30)
    return "\n".join(lines)


def get_weekday_name(dt: datetime):
    weekday = dt.weekday()
    if weekday == 6:
        return None
    return DAY_BY_NUM.get(weekday)


# ─── Клавиатуры ─────────────────────────────────────────
def main_keyboard():
    """Главная клавиатура. Текст кнопок — простой, без эмодзи."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Сегодня"), KeyboardButton(text="Завтра")],
            [KeyboardButton(text="На неделю")],
            [KeyboardButton(text="На дату")],
        ],
        resize_keyboard=True,
    )


# ─── Обработчики команд ─────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    week = get_current_week()
    week_label = get_week_label(week)
    await message.answer(
        f"👋 Привет! Я бот-расписание для группы <b>{GROUP}</b>.\n\n"
        f"📆 Сейчас: <b>{week_label}</b>\n\n"
        "Выберите действие:",
        reply_markup=main_keyboard(),
        parse_mode="HTML",
    )


@dp.message(Command("today"))
async def cmd_today(message: types.Message):
    today = datetime.now()
    day = get_weekday_name(today)
    if day:
        week = get_week_for_date(today)
        await message.answer(format_day(day, week), parse_mode="HTML")
    else:
        await message.answer("🎉 Сегодня воскресенье — выходной!")


@dp.message(Command("tomorrow"))
async def cmd_tomorrow(message: types.Message):
    tomorrow = datetime.now() + timedelta(days=1)
    day = get_weekday_name(tomorrow)
    if day:
        week = get_week_for_date(tomorrow)
        await message.answer(format_day(day, week), parse_mode="HTML")
    else:
        await message.answer("🎉 Завтра воскресенье — выходной!")


@dp.message(Command("week"))
async def cmd_week(message: types.Message):
    week = get_current_week()
    await message.answer(format_week(week), parse_mode="HTML")


@dp.message(Command("day"))
async def cmd_day(message: types.Message, state: FSMContext):
    await message.answer(
        "📅 <b>Введите дату в формате дд.мм</b>\n\n"
        "Например:\n"
        "• 22.09 — на этот год\n"
        "• 22.09.2026 — на конкретный год\n\n"
        "Или отправьте /cancel для отмены",
        parse_mode="HTML",
    )
    await state.set_state(ScheduleStates.waiting_for_date)


@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено.")


# ─── Обработчики кнопок (по ключевому слову) ────────────
# Используем .contains() — работает даже если эмодзи "сломается"

@dp.message(F.text.contains("Сегодня"))
async def btn_today(message: types.Message):
    await cmd_today(message)


@dp.message(F.text.contains("Завтра"))
async def btn_tomorrow(message: types.Message):
    await cmd_tomorrow(message)


@dp.message(F.text.contains("На неделю"))
async def btn_week(message: types.Message):
    await cmd_week(message)


@dp.message(F.text.contains("На дату"))
async def btn_date(message: types.Message, state: FSMContext):
    await cmd_day(message, state)


# ─── Ввод даты ──────────────────────────────────────────
@dp.message(ScheduleStates.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    date_str = message.text.strip()
    if not re.match(r'^\d{1,2}\.\d{1,2}(\.\d{2,4})?$', date_str):
        await message.answer(
            "❌ <b>Неверный формат!</b>\n\n"
            "Используйте:\n"
            "• дд.мм (например, 22.09)\n"
            "• дд.мм.гггг (например, 22.09.2026)\n\n"
            "Или /cancel для отмены",
            parse_mode="HTML",
        )
        return
    dt = parse_date(date_str)
    if not dt:
        await message.answer("❌ Не удалось распознать дату! Или /cancel", parse_mode="HTML")
        return
    day_name = get_weekday_name(dt)
    if not day_name:
        await message.answer("🎉 Это воскресенье — выходной!")
        await state.clear()
        return
    week = get_week_for_date(dt)
    week_label = get_week_label(week)
    date_formatted = dt.strftime("%d.%m.%Y")
    await message.answer(f"📅 <b>{day_name}, {date_formatted}</b> ({week_label})\n", parse_mode="HTML")
    await message.answer(format_day(day_name, week), parse_mode="HTML")
    await state.clear()


# ─── Запуск ─────────────────────────────────────────────
async def main():
    week = get_current_week()
    week_label = get_week_label(week)
    print(f" Бот расписания для {GROUP} запущен!")
    print(f"📆 Текущая неделя: {week_label}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())