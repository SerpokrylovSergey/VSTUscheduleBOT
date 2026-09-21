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
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv
from aiohttp import web

# ── Загрузка конфигурации ───────────────────────────────
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("Укажите BOT_TOKEN в файле .env")

try:
    with open("schedule.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    SCHEDULE = data["schedule"]
    GROUP = data["group"]
    print(f"✅ Расписание загружено для группы {GROUP}")
except Exception as e:
    print(f" Ошибка загрузки schedule.json: {e}")
    exit(1)

DAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
DAY_BY_NUM = {i: day for i, day in enumerate(DAYS)}

class ScheduleStates(StatesGroup):
    waiting_for_date = State()

bot = Bot(token=TOKEN)
dp = Dispatcher()

def get_current_week():
    return "week1" if datetime.now().isocalendar()[1] % 2 == 1 else "week2"

def get_week_for_date(dt: datetime):
    return "week1" if dt.isocalendar()[1] % 2 == 1 else "week2"

def get_week_label(week_key: str) -> str:
    return "Нечётная неделя" if week_key == "week1" else "Чётная неделя"

def parse_date(date_str: str, year: int = None) -> datetime | None:
    if year is None:
        year = datetime.now().year
    for fmt in ["%d.%m", "%d.%m.%Y", "%d.%m.%y"]:
        try:
            dt = datetime.strptime(date_str, fmt)
            if "%Y" not in fmt and "%y" not in fmt:
                dt = dt.replace(year=year)
            return dt
        except ValueError:
            continue
    return None

def format_pair(pair_num: str, pair_data: dict) -> str:
    lines = [f"🔹 <b>{pair_num} пара</b>"]
    if pair_data.get("subject"): lines.append(f"    {pair_data['subject']}")
    if pair_data.get("teacher"): lines.append(f"   👨‍🏫 {pair_data['teacher']}")
    if pair_data.get("room"): lines.append(f"   🚪 Ауд. {pair_data['room']}")
    return "\n".join(lines)

def format_day(day_name: str, week_key: str) -> str:
    week_label = get_week_label(week_key)
    header = f" <b>{day_name}</b> ({week_label})\n"
    if day_name not in SCHEDULE.get(week_key, {}) or not SCHEDULE[week_key][day_name]:
        return header + "\n😴 Нет занятий"
    pairs = SCHEDULE[week_key][day_name]
    sorted_pairs = sorted(pairs.keys(), key=lambda x: int(x))
    return header + "\n" + "\n\n".join([format_pair(p, pairs[p]) for p in sorted_pairs])

def format_week(week_key: str) -> str:
    week_label = get_week_label(week_key)
    lines = [f"📋 <b>Расписание на неделю — {GROUP}</b>", f"📆 <b>{week_label}</b>\n"]
    for day in DAYS:
        lines.append(format_day(day, week_key))
        lines.append("─" * 30)
    return "\n".join(lines)

def get_weekday_name(dt: datetime):
    return DAY_BY_NUM.get(dt.weekday()) if dt.weekday() != 6 else None

def main_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Сегодня"), KeyboardButton(text="Завтра")],
        [KeyboardButton(text="На неделю")],
        [KeyboardButton(text="На дату")],
    ], resize_keyboard=True)

# ─── Обработчики команд и кнопок ───────────────────────

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        f" Привет! Я бот-расписание для группы <b>{GROUP}</b>.\n\n"
        f"📆 Сейчас: <b>{get_week_label(get_current_week())}</b>\n\n"
        "Выберите действие:",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )

# Используем два декоратора вместо оператора |
@dp.message(Command("today"))
@dp.message(F.text.contains("Сегодня"))
async def cmd_today(message: types.Message):
    day = get_weekday_name(datetime.now())
    if day:
        await message.answer(format_day(day, get_current_week()), parse_mode="HTML")
    else:
        await message.answer("🎉 Сегодня воскресенье — выходной!")

@dp.message(Command("tomorrow"))
@dp.message(F.text.contains("Завтра"))
async def cmd_tomorrow(message: types.Message):
    tomorrow = datetime.now() + timedelta(days=1)
    day = get_weekday_name(tomorrow)
    if day:
        await message.answer(format_day(day, get_week_for_date(tomorrow)), parse_mode="HTML")
    else:
        await message.answer("🎉 Завтра воскресенье — выходной!")

@dp.message(Command("week"))
@dp.message(F.text.contains("На неделю"))
async def cmd_week(message: types.Message):
    await message.answer(format_week(get_current_week()), parse_mode="HTML")

@dp.message(Command("day"))
@dp.message(F.text.contains("На дату"))
async def cmd_day(message: types.Message, state: FSMContext):
    await message.answer(
        "📅 <b>Введите дату в формате дд.мм</b>\n"
        "(например, 22.09 или 22.09.2026)\n"
        "Или /cancel для отмены",
        parse_mode="HTML"
    )
    await state.set_state(ScheduleStates.waiting_for_date)

@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено.")

@dp.message(ScheduleStates.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    date_str = message.text.strip()
    if not re.match(r'^\d{1,2}\.\d{1,2}(\.\d{2,4})?$', date_str):
        await message.answer("❌ Неверный формат! Используйте дд.мм или /cancel", parse_mode="HTML")
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
    await message.answer(
        f"📅 <b>{day_name}, {dt.strftime('%d.%m.%Y')}</b> ({get_week_label(week)})\n",
        parse_mode="HTML"
    )
    await message.answer(format_day(day_name, week), parse_mode="HTML")
    await state.clear()

# ══════════════════════════════════════════════════════
# 🚀 ХАК ДЛЯ RENDER: Запуск веб-сервера + поллинг
# ═══════════════════════════════════════════════════════
async def on_startup(app):
    print("🤖 Запускаем Telegram бота (polling)...")
    asyncio.create_task(dp.start_polling(bot))

async def on_shutdown(app):
    await bot.session.close()

async def hello(request):
    return web.Response(text=f"✅ Бот {GROUP} работает 24/7!")

async def main():
    app = web.Application()
    app.router.add_get('/', hello)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    port = int(os.environ.get("PORT", 8080))
    print(f"🌐 Запуск веб-сервера на порту {port}...")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print("✅ Бот успешно запущен и готов к работе!")

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())