# -*- coding: utf-8 -*-
"""
Карманный математический инженер для зала.
Стек: aiogram 3.x, python-dotenv, Pillow (карточки), sqlite3 (аналитика).

Тон текстов: коротко, по делу, без эмодзи. Цифра — первой строкой.
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
import design
import storage
from design import num

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL", "thirstforfame1").lstrip("@")
CHANNEL_URL = f"https://t.me/{CHANNEL}"
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)  # свой user_id — для /stats
DB_PATH = os.getenv("DB_PATH", "bot.db")
design.CHANNEL = f"t.me/{CHANNEL}"  # подпись в подвале карточек

# Заполняется при старте из bot.get_me(): сменил бота в BotFather — ссылки поменялись сами.
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

# Последний результат каждого пользователя: функция, которая рисует его карточку.
# Только в памяти, до рестарта — callback_data ограничен 64 байтами.
_LAST_RESULT: dict[int, dict] = {}


# ---------------------------------------------------------------------------
# Кнопки. Один стиль: глагол или существительное, без эмодзи.
# ---------------------------------------------------------------------------

def _channel_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="Канал: разборы и программы", url=CHANNEL_URL)]


def _result_kb(kind: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Карточка", callback_data=f"card:{kind}")],
        _channel_row(),
    ])


def _start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[_channel_row()])


def _card_kb(kind: str) -> InlineKeyboardMarkup:
    """Под карточкой: оригинал без сжатия, позвать друга, канал."""
    rows = [[InlineKeyboardButton(text="Файл без сжатия", callback_data=f"file:{kind}")]]
    if BOT_USERNAME:
        rows.append([InlineKeyboardButton(text="Посчитать свой", url=f"https://t.me/{BOT_USERNAME}?start=card")])
    rows.append(_channel_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _remember(user_id: int, kind: str, render: Callable[[], bytes]) -> None:
    _LAST_RESULT[user_id] = {"kind": kind, "render": render}


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
    "<b>Карманный математический инженер для зала</b>\n"
    "Цифры между подходами — готовая математика. Без сайтов и регистрации.\n\n"
    "<b>Разовый максимум и рабочие веса</b>\n"
    "<code>100 8</code> — вес и повторы, без команды\n\n"
    "<b>RPE</b> — максимум по тяжести подхода\n"
    "<code>/rpe 140 3 8</code> — вес, повторы, RPE 6–10\n\n"
    "<b>Разминка</b> — подходы до рабочего веса\n"
    "<code>/warmup 140</code> — рабочий вес; гриф вторым числом\n\n"
    "<b>DOTS и Wilks</b> — сила с поправкой на вес тела\n"
    "<code>/dots м 90 500</code> — пол, вес тела, сумма\n"
    "<code>/wilks ж 62.5 280</code>\n\n"
    "<b>Разряд ЕВСК</b> — классическое троеборье\n"
    "<code>/rank м 90 500</code> — пол, вес тела, сумма\n\n"
    "<b>FFMI</b> — индекс сухой массы\n"
    "<code>/ffmi 180 85 15</code> — рост, вес, % жира\n\n"
    "<b>КБЖУ</b> — калории и БЖУ на день\n"
    "<code>/kbju м 30 180 85 3 сушка</code>\n"
    "пол, возраст, рост, вес, активность 1–5, цель: сушка / поддержание / масса\n\n"
    "Дробные — через точку или запятую. К каждому результату — кнопка «Карточка».\n"
    "В любом чате: <code>@{bot} 100 8</code>"
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
        "<b>Источники новых</b>",
    ]
    lines += [f"{src}: {cnt}" for src, cnt in s["sources"]] or ["—"]
    lines += ["", "<b>Действия</b>"]
    lines += [f"{kind}: {cnt}" for kind, cnt in s["events"]] or ["—"]
    await message.answer("\n".join(lines))


# ---------------------------------------------------------------------------
# Разбор аргументов
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
    raise ValueError("пол укажи как м или ж")


def _fail(text: str) -> str:
    """Единый вид ошибки ввода."""
    t = text.strip().rstrip(".")
    return f"Не получилось: {t[:1].lower() + t[1:]}."


def _usage(example: str, hint: str) -> str:
    return f"Формат: <code>{example}</code>\n{hint}"


_GOAL_MAP = {
    "сушка": "cut", "cut": "cut",
    "поддержание": "maintain", "maintain": "maintain",
    "масса": "bulk", "набор": "bulk", "bulk": "bulk",
}


# ---------------------------------------------------------------------------
# 1RM — быстрый путь: просто два числа без команды
# ---------------------------------------------------------------------------

_TWO_NUM_RE = re.compile(r"^\s*(-?\d+[.,]?\d*)\s*(?:[xх×на/]\s*)?(-?\d+[.,]?\d*)\s*$", re.IGNORECASE)


def _format_1rm(r: calc.OneRMResult) -> str:
    lines = [
        f"<b>1RM ≈ {num(r.average)} кг</b>",
        f"Подход: {num(r.weight)} кг × {r.reps}",
        "",
        f"Epley — {num(r.epley)} кг",
        f"Brzycki — {num(r.brzycki)} кг",
        f"Lombardi — {num(r.lombardi)} кг",
    ]
    if not r.reliable:
        lines.append("13+ повторов: формулы врут сильнее, бери с запасом.")
    lines += ["", "<b>Рабочие веса</b>"]
    lines += [f"{pct}% — {num(w)} кг" for pct, w in r.table]
    return "\n".join(lines)


async def _send_1rm(message: Message, weight: float, reps_f: float):
    reps = int(round(reps_f))
    if reps >= 37:  # формула Brzycki делит на (37 - повторы)
        await message.answer(_fail("для 37+ повторов разовый максимум не считается"))
        return
    try:
        r = calc.calc_1rm(weight, reps)
    except ValueError as e:
        await message.answer(_fail(str(e)))
        return
    _remember(message.from_user.id, "1rm", lambda: cards.card_1rm(r))
    _log(message.from_user.id, "1rm")
    await message.answer(_format_1rm(r), reply_markup=_result_kb("1rm"))


@dp.message(Command("rm"))
async def cmd_rm(message: Message):
    args = _args(message)
    if len(args) != 2:
        await message.answer(_usage("/rm 100 8", "вес, повторы"))
        return
    try:
        weight = calc.parse_number(args[0])
        reps = calc.parse_number(args[1])
    except ValueError:
        await message.answer(_fail("не разобрал числа. Пример: /rm 100 8"))
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
# Inline-режим: "@bot 100 8" в любом чате. Включается в BotFather: /setinline.
# Главный канал «сарафана»: результат уходит в чат друга с подписью бота.
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
            text = _format_1rm(r) + f"\n\nПосчитано в @{BOT_USERNAME}"
            results.append(
                InlineQueryResultArticle(
                    id=f"1rm:{weight:g}:{reps}",
                    title=f"1RM ≈ {num(r.average)} кг",
                    description=f"{num(weight)} кг × {reps} — максимум и рабочие веса",
                    input_message_content=InputTextMessageContent(message_text=text, parse_mode=ParseMode.HTML),
                )
            )
            _log(query.from_user.id, "inline")
    if not results:
        results.append(
            InlineQueryResultArticle(
                id="hint",
                title="Вес и повторы, например: 100 8",
                description="Посчитаю разовый максимум и рабочие веса",
                input_message_content=InputTextMessageContent(
                    message_text=f"Разовый максимум по подходу: @{BOT_USERNAME}"
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
        await message.answer(_usage(f"/{kind} м 90 500", "пол, вес тела, сумма"))
        return
    try:
        sex = _norm_sex(args[0])
        bw = calc.parse_number(args[1])
        total = calc.parse_number(args[2])
        dots = calc.calc_dots(sex, bw, total)
        wilks = calc.calc_wilks(sex, bw, total)
    except ValueError as e:
        await message.answer(_fail(str(e)))
        return

    main, other = (("DOTS", dots), ("Wilks", wilks)) if kind == "dots" else (("Wilks", wilks), ("DOTS", dots))
    sex_label = "мужчина" if sex == "m" else "женщина"
    text = (
        f"<b>{main[0]} {num(main[1])}</b>\n"
        f"{sex_label.capitalize()} · вес тела {num(bw)} кг · сумма {num(total)} кг\n"
        f"{other[0]} — {num(other[1])}"
    )
    _remember(message.from_user.id, kind, lambda: cards.card_strength(sex, bw, total, dots, wilks, kind))
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
        await message.answer(_usage("/ffmi 180 85 15", "рост в см, вес в кг, % жира"))
        return
    try:
        height = calc.parse_number(args[0])
        weight = calc.parse_number(args[1])
        bf = calc.parse_number(args[2])
        r = calc.calc_ffmi(height, weight, bf)
    except ValueError as e:
        await message.answer(_fail(str(e)))
        return

    text = (
        f"<b>FFMI {num(r.normalized_ffmi)}</b> (без поправки на рост {num(r.ffmi)})\n"
        f"Сухая масса — {num(r.lean_mass)} кг\n"
        f"{r.verdict.capitalize()}.\n\n"
        f"Точность упирается в замер % жира: на глаз — плюс-минус несколько единиц."
    )
    _remember(message.from_user.id, "ffmi", lambda: cards.card_ffmi(height, weight, bf, r))
    _log(message.from_user.id, "ffmi")
    await message.answer(text, reply_markup=_result_kb("ffmi"))


# ---------------------------------------------------------------------------
# КБЖУ
# ---------------------------------------------------------------------------

@dp.message(Command("kbju"))
async def cmd_kbju(message: Message):
    args = _args(message)
    if len(args) != 6:
        await message.answer(_usage(
            "/kbju м 30 180 85 3 сушка",
            "пол, возраст, рост, вес, активность 1–5, цель: сушка / поддержание / масса",
        ))
        return
    try:
        sex = _norm_sex(args[0])
        age = int(calc.parse_number(args[1]))
        height = calc.parse_number(args[2])
        weight = calc.parse_number(args[3])
        activity = int(calc.parse_number(args[4]))
        goal_raw = args[5].strip().lower()
        if goal_raw not in _GOAL_MAP:
            raise ValueError("цель — сушка, поддержание или масса")
        goal = _GOAL_MAP[goal_raw]
        # Миффлин-Сан Жеор выведена на взрослых, а дефицит калорий растущему
        # организму без врача давать нельзя — поэтому до 18 лет «сушку»
        # не считаем, показываем поддержание с объяснением.
        teen_note = None
        if age < 18:
            teen_note = "До 18 лет — грубый ориентир."
            if goal == "cut":
                goal = "maintain"
                teen_note += " Дефицит без врача не считаю: показано поддержание."
        r = calc.calc_kbju(sex, age, height, weight, activity, goal)
    except ValueError as e:
        await message.answer(_fail(str(e)))
        return

    text = (
        f"<b>{num(r.target_kcal, 0)} ккал в день</b> — {r.goal_label}\n"
        f"Белки {num(r.protein_g, 0)} г · жиры {num(r.fat_g, 0)} г · углеводы {num(r.carbs_g, 0)} г\n\n"
        f"В покое — {num(r.bmr, 0)} ккал, с активностью — {num(r.tdee, 0)} ккал\n"
        f"Активность: {r.activity_label}"
    )
    if teen_note:
        text += f"\n\n{teen_note}"
    _remember(message.from_user.id, "kbju", lambda: cards.card_kbju(weight, r, teen_note))
    _log(message.from_user.id, "kbju")
    await message.answer(text, reply_markup=_result_kb("kbju"))


# ---------------------------------------------------------------------------
# RPE
# ---------------------------------------------------------------------------

@dp.message(Command("rpe"))
async def cmd_rpe(message: Message):
    args = _args(message)
    if len(args) != 3:
        await message.answer(_usage("/rpe 140 3 8", "вес, повторы, RPE от 6 до 10"))
        return
    try:
        weight = calc.parse_number(args[0])
        reps = calc.parse_number(args[1])
        rpe = calc.parse_number(args[2])
        r = calc.calc_rpe(weight, reps, rpe)
    except ValueError as e:
        await message.answer(_fail(str(e)))
        return

    lines = [
        f"<b>1RM ≈ {num(r.estimated_1rm)} кг</b>",
        f"Подход: {num(r.weight)} кг × {r.reps} на RPE {num(r.rpe_used)}",
    ]
    if r.rpe_used != r.rpe:
        lines.append(f"RPE {num(r.rpe)} округлён до {num(r.rpe_used)}: шаг таблицы 0.5")
    lines += ["", f"<b>{r.reps} повт. на другом RPE</b>"]
    lines += [f"RPE {num(x)} — {num(w)} кг" for x, w in r.projection]
    _remember(message.from_user.id, "rpe", lambda: cards.card_rpe(r))
    _log(message.from_user.id, "rpe")
    await message.answer("\n".join(lines), reply_markup=_result_kb("rpe"))


# ---------------------------------------------------------------------------
# Разминка
# ---------------------------------------------------------------------------

@dp.message(Command("warmup"))
async def cmd_warmup(message: Message):
    args = _args(message)
    if len(args) not in (1, 2):
        await message.answer(_usage("/warmup 140", "рабочий вес; свой гриф — вторым числом: /warmup 140 15"))
        return
    try:
        work_weight = calc.parse_number(args[0])
        bar_weight = calc.parse_number(args[1]) if len(args) == 2 else 20.0
        steps = calc.generate_warmup(work_weight, bar_weight)
    except ValueError as e:
        await message.answer(_fail(str(e)))
        return

    lines = [f"<b>Разминка до {num(work_weight)} кг</b>", f"Гриф {num(bar_weight)} кг", ""]
    for step in steps:
        if step.reps:
            lines.append(f"{step.label} — {num(step.weight)} кг × {step.reps}")
        else:
            lines.append(f"<b>{step.label} — {num(step.weight)} кг</b>")
    _remember(message.from_user.id, "warmup", lambda: cards.card_warmup(work_weight, bar_weight, steps))
    _log(message.from_user.id, "warmup")
    await message.answer("\n".join(lines), reply_markup=_result_kb("warmup"))


# ---------------------------------------------------------------------------
# Разряд ЕВСК (классическое троеборье, без экипировки)
# ---------------------------------------------------------------------------

def _rank_ladder(sex: str, bodyweight: float) -> list[tuple[str, float | None]]:
    """Нормативы весовой категории — для карточки. Таблицы из calculators не меняются."""
    table = calc._RANK_TABLE_M if sex == "m" else calc._RANK_TABLE_F
    cats = sorted(table)
    cat = next((c for c in cats if bodyweight <= c), cats[-1])
    return [(name, table[cat][name]) for name in calc._RANK_ORDER]


@dp.message(Command("rank"))
async def cmd_rank(message: Message):
    args = _args(message)
    if len(args) != 3:
        await message.answer(_usage("/rank м 90 500", "пол, вес тела, сумма троеборья"))
        return
    try:
        sex = _norm_sex(args[0])
        bw = calc.parse_number(args[1])
        total = calc.parse_number(args[2])
        r = calc.calc_rank(sex, bw, total)
    except ValueError as e:
        await message.answer(_fail(str(e)))
        return

    head = f"<b>Разряд: {r.rank}</b>" if r.rank != "нет разряда" else "<b>Разряда пока нет</b> — ниже III юношеского"
    lines = [head, f"Категория до {r.weight_class} кг · сумма {num(total)} кг"]
    if r.next_rank:
        lines.append(f"До {r.next_rank} — {num(r.gap_to_next)} кг")
    lines += ["", "Классика, нормативы ЕВСК с поправками 2023–2024. Разряд присваивают по протоколу соревнований."]
    ladder = _rank_ladder(sex, bw)
    _remember(message.from_user.id, "rank", lambda: cards.card_rank(sex, bw, total, r, ladder))
    _log(message.from_user.id, "rank")
    await message.answer("\n".join(lines), reply_markup=_result_kb("rank"))


# ---------------------------------------------------------------------------
# Карточка: фото для превью в чате + по кнопке — файл без сжатия
# ---------------------------------------------------------------------------

def _render(user_id: int):
    data = _LAST_RESULT.get(user_id)
    if not data:
        return None, None
    return data["kind"], data["render"]()


@dp.callback_query(F.data.startswith("card:"))
async def make_card(callback: CallbackQuery):
    kind, png = _render(callback.from_user.id)
    if png is None:
        await callback.answer("Результат устарел — посчитай заново", show_alert=True)
        return
    _log(callback.from_user.id, f"card_{kind}")
    # Фото, а не документ: в чате сразу видно картинку, главная цифра читается в превью.
    await callback.message.answer_photo(
        BufferedInputFile(png, filename=f"{kind}.png"),
        caption="Перешли другу — пусть посчитает свой.",
        reply_markup=_card_kb(kind),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("file:"))
async def make_card_file(callback: CallbackQuery):
    kind, png = _render(callback.from_user.id)
    if png is None:
        await callback.answer("Результат устарел — посчитай заново", show_alert=True)
        return
    _log(callback.from_user.id, f"file_{kind}")
    await callback.message.answer_document(BufferedInputFile(png, filename=f"{kind}.png"))
    await callback.answer()


# ---------------------------------------------------------------------------
# Глобальный обработчик ошибок: неожиданное падение хендлера — в лог, бот живёт дальше
# ---------------------------------------------------------------------------

@dp.error()
async def on_error(event):
    logger.error("Необработанное исключение при обработке апдейта", exc_info=event.exception)
    return True


# ---------------------------------------------------------------------------
# Меню команд (кнопка «Меню» рядом с полем ввода)
# ---------------------------------------------------------------------------

BOT_COMMANDS = [
    BotCommand(command="rm", description="Разовый максимум и рабочие веса"),
    BotCommand(command="rpe", description="Максимум по RPE"),
    BotCommand(command="warmup", description="Разминка до рабочего веса"),
    BotCommand(command="dots", description="DOTS — сила с поправкой на вес"),
    BotCommand(command="wilks", description="Wilks — сила с поправкой на вес"),
    BotCommand(command="rank", description="Разряд ЕВСК по сумме троеборья"),
    BotCommand(command="ffmi", description="FFMI — индекс сухой массы"),
    BotCommand(command="kbju", description="Калории и БЖУ на день"),
    BotCommand(command="help", description="Все команды"),
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
