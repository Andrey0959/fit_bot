# -*- coding: utf-8 -*-
"""
Карманный математический инженер для зала.
Стек: aiogram 3.x, python-dotenv, Pillow (карточки).

Запуск: см. README.md
"""

import asyncio
import logging
import os
import re
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from dotenv import load_dotenv

import calculators as calc
import cards

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
BRAND = os.getenv("BRAND_TAG", "@thirstforfame1")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),  # видно в терминале / логах Railway как раньше
        RotatingFileHandler(
            "bot.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        ),  # + свой файл рядом с bot.py, максимум ~8 МБ суммарно (4 файла по 2 МБ)
    ],
)
logger = logging.getLogger(__name__)
dp = Dispatcher()

# В памяти храним последний результат каждого юзера, чтобы по кнопке
# "Сделать карточку" не пересчитывать и не гонять данные через callback_data
# (там лимит 64 байта). Никакой персистентности, всё живёт до рестарта.
_LAST_RESULT: dict[int, dict] = {}


def _card_button(kind: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🖼 Сделать карточку", callback_data=f"card:{kind}")]]
    )


# Ориентировочные шкалы уровня для карточек (DOTS/Wilks и FFMI) — границы
# приблизительные, для наглядности на картинке, не претендуют на строгую
# классификацию федераций.
_STRENGTH_GAUGE = {"min": 100, "max": 600, "labels": ["Новичок", "Любитель", "Продвинутый", "Элита", "Топ"]}
_FFMI_GAUGE = {"min": 15, "max": 28, "labels": ["Низкий", "Средний", "Хороший", "Предел", "Выше"]}


# ---------------------------------------------------------------------------
# /start, /help
# ---------------------------------------------------------------------------

HELP_TEXT = (
    "🏋️ <b>Карманный математический инженер для зала</b>\n"
    "<i>Кидаешь цифры между подходами — получаешь готовую математику. Без сайтов, без регистраций.</i>\n\n"
    "━━━━━━━━━━━━━━━\n\n"
    "💪 <b>Разовый максимум + раскладка по %</b>\n"
    "Просто напиши: <code>100 8</code>\n"
    "<i>(вес и повторы — без команды, самый быстрый путь)</i>\n\n"
    "⚖️ <b>DOTS</b> — сила с поправкой на вес тела\n"
    "<code>/dots м 90 500</code>\n"
    "<i>(пол, вес атлета, сумма/вес на штанге)</i>\n\n"
    "🏆 <b>Wilks</b> — старый привычный коэффициент\n"
    "<code>/wilks ж 62.5 280</code>\n\n"
    "📏 <b>FFMI</b> — индекс сухой массы\n"
    "<code>/ffmi 180 85 15</code>\n"
    "<i>(рост см, вес кг, % жира)</i>\n\n"
    "🍗 <b>КБЖУ</b> — калории и БЖУ (Миффлин-Сан Жеор)\n"
    "<code>/kbju м 30 180 85 3 сушка</code>\n"
    "<i>(пол, возраст, рост см, вес кг, активность 1-5, цель)</i>\n\n"
    "🔥 <b>RPE</b> — оценка 1ПМ по тяжести подхода\n"
    "<code>/rpe 140 3 8</code>\n"
    "<i>(вес, повторы, RPE от 6 до 10)</i>\n\n"
    "🔧 <b>Разминка</b> — лестница до рабочего веса\n"
    "<code>/warmup 140</code>\n"
    "<i>(рабочий вес; свой гриф — вторым числом)</i>\n\n"
    "━━━━━━━━━━━━━━━\n"
    "Дробные — через точку или запятую: <code>82.5</code> или <code>82,5</code>."
)


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(HELP_TEXT)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT)


# ---------------------------------------------------------------------------
# Утилита разбора аргументов команды
# ---------------------------------------------------------------------------

def _args(message: Message) -> list[str]:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return []
    return parts[1].split()


def _norm_sex(raw: str) -> str:
    raw = raw.strip().lower()
    if raw in ("м", "m", "муж", "male"):
        return "m"
    if raw in ("ж", "f", "жен", "female"):
        return "f"
    raise ValueError("Пол укажи как м/ж")


_GOAL_MAP = {
    "сушка": "cut", "cut": "cut",
    "поддержание": "maintain", "maintain": "maintain",
    "масса": "bulk", "набор": "bulk", "bulk": "bulk",
}


# ---------------------------------------------------------------------------
# 1RM — быстрый путь: просто два числа без команды
# ---------------------------------------------------------------------------

_TWO_NUM_RE = re.compile(r"^\s*(-?\d+[.,]?\d*)\s*(?:[xх×на/]\s*)?(-?\d+[.,]?\d*)\s*$", re.IGNORECASE)


async def _send_1rm(message: Message, weight: float, reps_f: float):
    reps = int(round(reps_f))
    try:
        r = calc.calc_1rm(weight, reps)
    except ValueError as e:
        await message.answer(f"⚠️ {e}")
        return

    lines = [f"<b>{weight:g} кг × {reps}</b>"]
    lines.append(f"1RM (Epley): {r.epley:.1f} кг")
    lines.append(f"1RM (Brzycki): {r.brzycki:.1f} кг")
    lines.append(f"1RM (Lombardi): {r.lombardi:.1f} кг")
    lines.append(f"<b>Среднее: {r.average:.1f} кг</b>")
    if not r.reliable:
        lines.append("⚠️ При {}+ повторах формулы врут сильнее — бери с запасом.".format(13))
    lines.append("")
    lines.append("<b>Рабочие веса:</b>")
    for pct, w in r.table:
        lines.append(f"{pct}% — {w:g} кг")

    _LAST_RESULT[message.from_user.id] = {
        "kind": "1rm",
        "weight": weight,
        "reps": reps,
        "average": r.average,
        "table": r.table,
    }
    await message.answer("\n".join(lines), reply_markup=_card_button("1rm"))


@dp.message(Command("rm"))
async def cmd_rm(message: Message):
    args = _args(message)
    if len(args) != 2:
        await message.answer("Формат: <code>/rm 100 8</code> (вес, повторы)")
        return
    try:
        weight = calc.parse_number(args[0])
        reps = calc.parse_number(args[1])
    except ValueError:
        await message.answer("Не смог разобрать числа. Пример: <code>/rm 100 8</code>")
        return
    await _send_1rm(message, weight, reps)


@dp.message(F.text.regexp(_TWO_NUM_RE.pattern))
async def quick_1rm(message: Message):
    m = _TWO_NUM_RE.match(message.text)
    if not m:
        return
    try:
        weight = calc.parse_number(m.group(1))
        reps = calc.parse_number(m.group(2))
    except ValueError:
        return
    await _send_1rm(message, weight, reps)


# ---------------------------------------------------------------------------
# DOTS / Wilks
# ---------------------------------------------------------------------------

async def _strength_score(message: Message, kind: str):
    args = _args(message)
    if len(args) != 3:
        name = "dots" if kind == "dots" else "wilks"
        await message.answer(f"Формат: <code>/{name} м 90 500</code> (пол, вес атлета, сумма на штанге)")
        return
    try:
        sex = _norm_sex(args[0])
        bw = calc.parse_number(args[1])
        total = calc.parse_number(args[2])
    except ValueError as e:
        await message.answer(f"⚠️ {e}")
        return

    try:
        if kind == "dots":
            score = calc.calc_dots(sex, bw, total)
            label = "DOTS"
        else:
            score = calc.calc_wilks(sex, bw, total)
            label = "Wilks"
    except ValueError as e:
        await message.answer(f"⚠️ {e}")
        return

    sex_label = "мужчины" if sex == "m" else "женщины"
    text = (
        f"<b>{label}: {score:.1f}</b>\n"
        f"Вес атлета: {bw:g} кг · Сумма: {total:g} кг · {sex_label}"
    )
    _LAST_RESULT[message.from_user.id] = {
        "kind": kind,
        "score": score,
        "label": label,
        "sub_label": "Атлет",
        "sub_value": f"{bw:g} кг · сумма {total:g} кг",
        "gauge": _STRENGTH_GAUGE,
    }
    await message.answer(text, reply_markup=_card_button(kind))


@dp.message(Command("dots"))
async def cmd_dots(message: Message):
    await _strength_score(message, "dots")


@dp.message(Command("wilks"))
async def cmd_wilks(message: Message):
    await _strength_score(message, "wilks")


# ---------------------------------------------------------------------------
# FFMI
# ---------------------------------------------------------------------------

@dp.message(Command("ffmi"))
async def cmd_ffmi(message: Message):
    args = _args(message)
    if len(args) != 3:
        await message.answer("Формат: <code>/ffmi 180 85 15</code> (рост см, вес кг, % жира)")
        return
    try:
        height = calc.parse_number(args[0])
        weight = calc.parse_number(args[1])
        bf = calc.parse_number(args[2])
        r = calc.calc_ffmi(height, weight, bf)
    except ValueError as e:
        await message.answer(f"⚠️ {e}")
        return

    text = (
        f"<b>FFMI: {r.ffmi:.1f}</b> (норм. {r.normalized_ffmi:.1f})\n"
        f"Сухая масса: {r.lean_mass:.1f} кг\n"
        f"{r.verdict}\n\n"
        f"⚠️ Точность впрямую зависит от точности % жира — если мерил на глаз, погрешность может съесть выводы."
    )
    _LAST_RESULT[message.from_user.id] = {
        "kind": "ffmi",
        "score": r.normalized_ffmi,
        "label": "FFMI (норм.)",
        "sub_label": "Вывод",
        "sub_value": r.verdict,
        "gauge": _FFMI_GAUGE,
    }
    await message.answer(text, reply_markup=_card_button("ffmi"))


# ---------------------------------------------------------------------------
# КБЖУ
# ---------------------------------------------------------------------------

@dp.message(Command("kbju"))
async def cmd_kbju(message: Message):
    args = _args(message)
    if len(args) != 6:
        await message.answer(
            "Формат: <code>/kbju м 30 180 85 3 сушка</code>\n"
            "(пол, возраст, рост см, вес кг, активность 1-5, цель: сушка/поддержание/масса)"
        )
        return
    try:
        sex = _norm_sex(args[0])
        age = int(calc.parse_number(args[1]))
        height = calc.parse_number(args[2])
        weight = calc.parse_number(args[3])
        activity = int(calc.parse_number(args[4]))
        goal_raw = args[5].strip().lower()
        if goal_raw not in _GOAL_MAP:
            raise ValueError("Цель: сушка/поддержание/масса")
        goal = _GOAL_MAP[goal_raw]
        r = calc.calc_kbju(sex, age, height, weight, activity, goal)
    except ValueError as e:
        await message.answer(f"⚠️ {e}")
        return

    text = (
        f"<b>{r.target_kcal:.0f} ккал/день</b> — {r.goal_label}\n"
        f"BMR: {r.bmr:.0f} · TDEE: {r.tdee:.0f} · {r.activity_label}\n\n"
        f"Белки: {r.protein_g:.0f} г\n"
        f"Жиры: {r.fat_g:.0f} г\n"
        f"Углеводы: {r.carbs_g:.0f} г"
    )
    _LAST_RESULT[message.from_user.id] = {
        "kind": "kbju",
        "target": r.target_kcal,
        "protein": r.protein_g,
        "fat": r.fat_g,
        "carbs": r.carbs_g,
        "goal_label": r.goal_label,
    }
    await message.answer(text, reply_markup=_card_button("kbju"))


# ---------------------------------------------------------------------------
# RPE
# ---------------------------------------------------------------------------

@dp.message(Command("rpe"))
async def cmd_rpe(message: Message):
    args = _args(message)
    if len(args) != 3:
        await message.answer(
            "Формат: <code>/rpe 140 3 8</code> (вес, повторы, RPE от 6 до 10)"
        )
        return
    try:
        weight = calc.parse_number(args[0])
        reps = calc.parse_number(args[1])
        rpe = calc.parse_number(args[2])
        r = calc.calc_rpe(weight, reps, rpe)
    except ValueError as e:
        await message.answer(f"⚠️ {e}")
        return

    lines = [f"<b>{r.weight:g} кг × {r.reps} на RPE {r.rpe_used:g}</b>"]
    if r.rpe_used != r.rpe:
        lines.append(f"(округлил RPE {r.rpe:g} → {r.rpe_used:g}, шаг таблицы — 0.5)")
    lines.append(f"<b>Оценка 1ПМ: {r.estimated_1rm:.1f} кг</b>")
    lines.append("")
    lines.append(f"Тот же вес {r.reps} повторов на другой RPE:")
    for rpe_val, w in r.projection:
        lines.append(f"RPE {rpe_val:g} — {w:g} кг")

    await message.answer("\n".join(lines))


# ---------------------------------------------------------------------------
# Разминка
# ---------------------------------------------------------------------------

@dp.message(Command("warmup"))
async def cmd_warmup(message: Message):
    args = _args(message)
    if len(args) not in (1, 2):
        await message.answer(
            "Формат: <code>/warmup 140</code> (рабочий вес)\n"
            "Можно указать свой гриф: <code>/warmup 140 15</code>"
        )
        return
    try:
        work_weight = calc.parse_number(args[0])
        bar_weight = calc.parse_number(args[1]) if len(args) == 2 else 20.0
        steps = calc.generate_warmup(work_weight, bar_weight)
    except ValueError as e:
        await message.answer(f"⚠️ {e}")
        return

    lines = [f"<b>Разминка до {work_weight:g} кг</b>"]
    for step in steps:
        if step.reps:
            lines.append(f"{step.label}: {step.weight:g} кг × {step.reps}")
        else:
            lines.append(f"<b>{step.label}: {step.weight:g} кг</b>")

    await message.answer("\n".join(lines))


# ---------------------------------------------------------------------------
# Генерация карточки по кнопке
# ---------------------------------------------------------------------------

@dp.callback_query(F.data.startswith("card:"))
async def make_card(callback: CallbackQuery):
    data = _LAST_RESULT.get(callback.from_user.id)
    if not data:
        await callback.answer("Результат устарел, посчитай заново", show_alert=True)
        return

    kind = data["kind"]
    if kind == "1rm":
        png = cards.card_1rm(data["weight"], data["reps"], data["average"], data["table"], brand=BRAND)
    elif kind in ("dots", "wilks"):
        png = cards.card_score(data["label"], data["score"], data["sub_label"], data["sub_value"],
                                brand=BRAND, gauge=data.get("gauge"))
    elif kind == "ffmi":
        png = cards.card_score(data["label"], data["score"], data["sub_label"], data["sub_value"],
                                brand=BRAND, gauge=data.get("gauge"))
    elif kind == "kbju":
        png = cards.card_kbju(data["target"], data["protein"], data["fat"], data["carbs"], data["goal_label"], brand=BRAND)
    else:
        await callback.answer("Неизвестный тип", show_alert=True)
        return

    # Отправляем как документ, а не как фото: Telegram агрессивно пережимает
    # обычные фото (падает резкость текста на карточке), а документ уходит
    # без потери качества — то, что нужно для карточки под соцсети.
    photo = BufferedInputFile(png, filename="card.png")
    await callback.message.answer_document(photo)
    await callback.answer()


# ---------------------------------------------------------------------------
# Глобальный обработчик ошибок — ловит любое неожиданное падение хендлера
# (не только ValueError, который мы уже обрабатываем точечно) и пишет его
# в лог (консоль + bot.log), чтобы баг не проходил тихо мимо.
# ---------------------------------------------------------------------------

@dp.error()
async def on_error(event):
    logger.error("Необработанное исключение при обработке апдейта", exc_info=event.exception)
    return True  # подавляем дальнейшее всплытие, чтобы бот не падал целиком


# ---------------------------------------------------------------------------
# Меню команд (кнопка "Меню" в Telegram рядом с полем ввода)
# ---------------------------------------------------------------------------

BOT_COMMANDS = [
    BotCommand(command="rm", description="💪 1RM + раскладка по % (вес, повторы)"),
    BotCommand(command="dots", description="⚖️ DOTS: пол, вес атлета, сумма"),
    BotCommand(command="wilks", description="🏆 Wilks: пол, вес атлета, сумма"),
    BotCommand(command="ffmi", description="📏 FFMI: рост, вес, % жира"),
    BotCommand(command="kbju", description="🍗 КБЖУ: пол, возраст, рост, вес, активность, цель"),
    BotCommand(command="rpe", description="🔥 Оценка 1ПМ по RPE: вес, повторы, RPE"),
    BotCommand(command="warmup", description="🔧 Разминка до рабочего веса"),
    BotCommand(command="help", description="ℹ️ Как пользоваться ботом"),
]


async def main():
    if not TOKEN:
        raise SystemExit("Не найден BOT_TOKEN. Положи его в .env (см. README.md)")
    _init_db()
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.set_my_commands(BOT_COMMANDS)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
