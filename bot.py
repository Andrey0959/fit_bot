# -*- coding: utf-8 -*-
"""
Карманный математический инженер для зала.
Стек: aiogram 3.x, python-dotenv, Pillow (карточки), sqlite3 (аналитика).

Запуск: см. README.md
"""

import asyncio
import logging
import os
import re
from logging.handlers import RotatingFileHandler
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    BotCommand,
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
    TelegramObject,
    User,
)
from dotenv import load_dotenv

import calculators as calc
import cards
import storage

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL", "thirstforfame1").lstrip("@")
CHANNEL_URL = f"https://t.me/{CHANNEL}"
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)  # свой user_id — для /stats
DB_PATH = os.getenv("DB_PATH", "bot.db")

# Заполняется при старте из bot.get_me(), чтобы не хардкодить username:
# сменил бота в BotFather — подпись на карточках поменялась сама.
BOT_USERNAME = ""

_log_handlers: list[logging.Handler] = [logging.StreamHandler()]  # консоль / логи хостинга
try:
    # Файл логов (максимум ~8 МБ: 4 файла по 2 МБ). На хостингах с диском
    # "только для чтения" (Deployka) кладём его через LOG_PATH в /data,
    # а если писать некуда — работаем только с консолью, а не падаем.
    _log_handlers.append(RotatingFileHandler(
        os.getenv("LOG_PATH", "bot.log"), maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    ))
except OSError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=_log_handlers,
)
logger = logging.getLogger(__name__)
dp = Dispatcher()

# В памяти храним последний результат каждого юзера, чтобы по кнопке
# "Сделать карточку" не пересчитывать и не гонять данные через callback_data
# (там лимит 64 байта). Никакой персистентности, всё живёт до рестарта.
_LAST_RESULT: dict[int, dict] = {}


def _brand() -> str:
    """Подпись в подвале карточки: канал + бот, чтобы по пересланной
    картинке можно было найти и то и другое."""
    return f"@{CHANNEL} · @{BOT_USERNAME}" if BOT_USERNAME else f"@{CHANNEL}"


def _channel_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="📢 Канал: разборы и программы", url=CHANNEL_URL)]


def _result_kb(kind: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🖼 Сделать карточку", callback_data=f"card:{kind}")],
            _channel_row(),
        ]
    )


def _start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[_channel_row()])


def _share_kb() -> InlineKeyboardMarkup:
    """Под карточкой: подпись зовёт друга посчитать свой — значит первая
    кнопка должна вести в бота, а не только в канал."""
    rows = []
    if BOT_USERNAME:
        rows.append([InlineKeyboardButton(
            text="🧮 Посчитать свой", url=f"https://t.me/{BOT_USERNAME}?start=card"
        )])
    rows.append(_channel_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


# Ориентировочные шкалы уровня для карточек (DOTS/Wilks и FFMI) — для
# наглядности, не строгая классификация федераций.
_STRENGTH_GAUGE = {"min": 100, "max": 600, "labels": ["Новичок", "Любитель", "Продвинутый", "Элита", "Топ"]}
_FFMI_GAUGE = {"min": 15, "max": 28, "labels": ["Низкий", "Средний", "Хороший", "Предел", "Выше"]}


# ---------------------------------------------------------------------------
# Аналитика: каждый апдейт обновляет last_seen пользователя.
# Ошибка БД не должна ронять ответ пользователю — поэтому только логируем.
# ---------------------------------------------------------------------------

class TrackUsersMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user:
            try:
                storage.touch_user(user.id)
            except Exception:
                logger.exception("Не удалось обновить пользователя в БД")
        return await handler(event, data)


def _log(user_id: int, kind: str) -> None:
    try:
        storage.log_event(user_id, kind)
    except Exception:
        logger.exception("Не удалось записать событие %s", kind)


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
    "🏅 <b>Разряд ЕВСК</b> — по сумме троеборья и весу\n"
    "<code>/rank м 90 500</code>\n"
    "<i>(пол, вес атлета, сумма троеборья)</i>\n\n"
    "━━━━━━━━━━━━━━━\n"
    "Дробные — через точку или запятую: <code>82.5</code> или <code>82,5</code>.\n\n"
    "💡 Считать можно прямо в любом чате: напиши <code>@{bot} 100 8</code>"
)


def _help_text() -> str:
    return HELP_TEXT.replace("{bot}", BOT_USERNAME or "бот")


@dp.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    # t.me/bot?start=vk_clip1 -> source="vk_clip1": так видно, какой ролик/пост привёл людей
    source = (command.args or "").strip()[:64] or None
    if source:
        try:
            storage.touch_user(message.from_user.id, source)
        except Exception:
            logger.exception("Не удалось сохранить источник")
    _log(message.from_user.id, "start")
    await message.answer(_help_text(), reply_markup=_start_kb())


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(_help_text(), reply_markup=_start_kb())


# ---------------------------------------------------------------------------
# /stats — только для владельца (ADMIN_ID в .env)
# ---------------------------------------------------------------------------

@dp.message(Command("stats"))
async def cmd_stats(message: Message, command: CommandObject):
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        return
    days = 7
    if command.args and command.args.strip().isdigit():
        days = max(1, min(int(command.args.strip()), 365))
    s = storage.stats(days)
    lines = [
        f"<b>Статистика за {days} дн.</b>",
        f"Всего пользователей: {s['total']}",
        f"Новых: {s['new']}",
        f"Активных: {s['active']}",
        "",
        "<b>Источники новых:</b>",
    ]
    lines += [f"{src}: {cnt}" for src, cnt in s["sources"]] or ["—"]
    lines += ["", "<b>Действия:</b>"]
    lines += [f"{kind}: {cnt}" for kind, cnt in s["events"]] or ["—"]
    await message.answer("\n".join(lines))


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


def _format_1rm(weight: float, reps: int, r: calc.OneRMResult) -> str:
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
    return "\n".join(lines)


async def _send_1rm(message: Message, weight: float, reps_f: float):
    reps = int(round(reps_f))
    try:
        r = calc.calc_1rm(weight, reps)
    except ValueError as e:
        await message.answer(f"⚠️ {e}")
        return

    _LAST_RESULT[message.from_user.id] = {
        "kind": "1rm",
        "weight": weight,
        "reps": reps,
        "average": r.average,
        "table": r.table,
    }
    _log(message.from_user.id, "1rm")
    await message.answer(_format_1rm(weight, reps, r), reply_markup=_result_kb("1rm"))


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
# Inline-режим: "@bot 100 8" в любом чате. Нужно один раз включить
# в BotFather: /setinline -> выбрать бота -> подсказка "вес повторы".
# Это главный канал "сарафана": результат уходит в чат друга с подписью бота.
# ---------------------------------------------------------------------------

@dp.inline_query()
async def inline_1rm(query: InlineQuery):
    m = _TWO_NUM_RE.match(query.query or "")
    results = []
    if m:
        try:
            weight = calc.parse_number(m.group(1))
            reps = int(round(calc.parse_number(m.group(2))))
            r = calc.calc_1rm(weight, reps)
        except ValueError:
            r = None
        if r:
            text = _format_1rm(weight, reps, r) + f"\n\nПосчитано в @{BOT_USERNAME}"
            results.append(
                InlineQueryResultArticle(
                    id=f"1rm:{weight:g}:{reps}",
                    title=f"Максимум ≈ {r.average:.1f} кг",
                    description=f"{weight:g} кг × {reps} → 1RM и рабочие веса по %",
                    input_message_content=InputTextMessageContent(
                        message_text=text, parse_mode=ParseMode.HTML
                    ),
                )
            )
            _log(query.from_user.id, "inline")
    if not results:
        results.append(
            InlineQueryResultArticle(
                id="hint",
                title="Напиши вес и повторы, например: 100 8",
                description="Посчитаю разовый максимум и рабочие веса",
                input_message_content=InputTextMessageContent(
                    message_text=f"Считаю разовый максимум по подходу: @{BOT_USERNAME}"
                ),
            )
        )
    await query.answer(results, cache_time=60, is_personal=False)


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
    _log(message.from_user.id, kind)
    await message.answer(text, reply_markup=_result_kb(kind))


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
    _log(message.from_user.id, "ffmi")
    await message.answer(text, reply_markup=_result_kb("ffmi"))


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
        # Миффлин-Сан Жеор выведена на взрослых, а дефицит калорий растущему
        # организму без врача давать нельзя — поэтому до 18 лет "сушку"
        # не считаем, показываем поддержание с объяснением.
        teen_note = ""
        if age < 18:
            teen_note = "\n\n⚠️ Формула рассчитана на взрослых — до 18 лет это лишь грубый ориентир."
            if goal == "cut":
                goal = "maintain"
                teen_note += " Дефицит калорий подросткам без врача не считаю — показал поддержание."
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
        f"{teen_note}"
    )
    _LAST_RESULT[message.from_user.id] = {
        "kind": "kbju",
        "target": r.target_kcal,
        "protein": r.protein_g,
        "fat": r.fat_g,
        "carbs": r.carbs_g,
        "goal_label": r.goal_label,
    }
    _log(message.from_user.id, "kbju")
    await message.answer(text, reply_markup=_result_kb("kbju"))


# ---------------------------------------------------------------------------
# RPE
# ---------------------------------------------------------------------------

@dp.message(Command("rpe"))
async def cmd_rpe(message: Message):
    args = _args(message)
    if len(args) != 3:
        await message.answer("Формат: <code>/rpe 140 3 8</code> (вес, повторы, RPE от 6 до 10)")
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

    _log(message.from_user.id, "rpe")
    await message.answer("\n".join(lines), reply_markup=_start_kb())


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

    _log(message.from_user.id, "warmup")
    await message.answer("\n".join(lines), reply_markup=_start_kb())


# ---------------------------------------------------------------------------
# Разряд ЕВСК (классическое троеборье, без экипировки)
# ---------------------------------------------------------------------------

@dp.message(Command("rank"))
async def cmd_rank(message: Message):
    args = _args(message)
    if len(args) != 3:
        await message.answer("Формат: <code>/rank м 90 500</code> (пол, вес атлета, сумма троеборья)")
        return
    try:
        sex = _norm_sex(args[0])
        bw = calc.parse_number(args[1])
        total = calc.parse_number(args[2])
        r = calc.calc_rank(sex, bw, total)
    except ValueError as e:
        await message.answer(f"⚠️ {e}")
        return

    lines = [f"<b>Весовая категория: до {r.weight_class} кг</b>"]
    if r.rank == "нет разряда":
        lines.append("Норматив ниже III юношеского — официального разряда пока нет")
    else:
        lines.append(f"<b>Разряд: {r.rank}</b>")
    if r.next_rank:
        lines.append(f"До «{r.next_rank}» не хватает {r.gap_to_next:.1f} кг")
    lines.append("")
    lines.append(
        "<i>Классическое троеборье (без экипировки), ЕВСК с учётом поправок 2023-2024 гг. "
        "Разряд присваивается по официальному протоколу соревнований — здесь только ориентир.</i>"
    )

    _log(message.from_user.id, "rank")
    await message.answer("\n".join(lines), reply_markup=_start_kb())


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
    brand = _brand()
    if kind == "1rm":
        png = cards.card_1rm(data["weight"], data["reps"], data["average"], data["table"], brand=brand)
    elif kind in ("dots", "wilks", "ffmi"):
        png = cards.card_score(data["label"], data["score"], data["sub_label"], data["sub_value"],
                               brand=brand, gauge=data.get("gauge"))
    elif kind == "kbju":
        png = cards.card_kbju(data["target"], data["protein"], data["fat"], data["carbs"], data["goal_label"], brand=brand)
    else:
        await callback.answer("Неизвестный тип", show_alert=True)
        return

    # Отправляем как документ, а не как фото: Telegram агрессивно пережимает
    # обычные фото (падает резкость текста на карточке), а документ уходит
    # без потери качества — то, что нужно для карточки под соцсети.
    photo = BufferedInputFile(png, filename="card.png")
    _log(callback.from_user.id, f"card_{kind}")
    await callback.message.answer_document(
        photo,
        caption="Перешли другу — пусть посчитает свой 👇",
        reply_markup=_share_kb(),
    )
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
    BotCommand(command="rank", description="🏅 Разряд ЕВСК по сумме троеборья"),
    BotCommand(command="help", description="ℹ️ Как пользоваться ботом"),
]


async def main():
    global BOT_USERNAME
    if not TOKEN:
        raise SystemExit("Не найден BOT_TOKEN. Положи его в .env (см. README.md)")
    storage.init(DB_PATH)
    dp.update.outer_middleware(TrackUsersMiddleware())
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    BOT_USERNAME = me.username
    logger.info("Бот @%s, канал @%s, БД %s", BOT_USERNAME, CHANNEL, DB_PATH)
    await bot.set_my_commands(BOT_COMMANDS)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
