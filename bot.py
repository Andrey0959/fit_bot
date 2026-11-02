# -*- coding: utf-8 -*-
"""
Карманный математический инженер для зала.
Стек: aiogram 3.x, python-dotenv, Pillow (карточки), sqlite3 (аналитика).
Сценарии калькуляторов и тексты результатов — в wizard.py.

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
from aiogram.exceptions import TelegramBadRequest
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
    MenuButtonWebApp,
    Message,
    TelegramObject,
    User,
    WebAppInfo,
)
from dotenv import load_dotenv

import calculators as calc
import design
import storage
import wizard
from design import num

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL", "thirstforfame1").lstrip("@")
CHANNEL_URL = f"https://t.me/{CHANNEL}"
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)  # свой user_id — для /stats
DB_PATH = os.getenv("DB_PATH", "bot.db")
# Мини-приложение (GitHub Pages). Пустая строка — кнопки приложения не показываются.
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://andrey0959.github.io/fit_bot/").strip()
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

# Пошаговый сценарий: {user_id: {"tool", "step", "data", "chat", "msg", "result"}}.
# И последние ответы для кнопки «как в прошлый раз» — тоже только в памяти, на диск не пишем.
_FLOW: dict[int, dict] = {}
_LAST_INPUT: dict[int, dict] = {}


# ---------------------------------------------------------------------------
# Кнопки. Текст без эмодзи; эмодзи только в навигации: ⬅️ Назад и 🏠 Меню.
# ---------------------------------------------------------------------------

def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _channel_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="Канал автора", url=CHANNEL_URL)]


def _nav_row(back: bool = True) -> list[InlineKeyboardButton]:
    row = [_btn("⬅️ Назад", "nav:back")] if back else []
    return row + [_btn("🏠 Меню", "nav:menu")]


def _main_kb() -> InlineKeyboardMarkup:
    rows = [
        [_btn("Сила", "sec:strength"), _btn("Пауэрлифтинг", "sec:pl")],
        [_btn("Тело и питание", "sec:body")],
        [_btn("📖 Объяснение терминов", "gl")],
    ]
    if WEBAPP_URL:
        rows.append([InlineKeyboardButton(text="Открыть калькулятор", web_app=WebAppInfo(url=WEBAPP_URL))])
    rows.append(_channel_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _section_kb(section: str) -> InlineKeyboardMarkup:
    _, tools = wizard.SECTIONS[section]
    rows = [[_btn(wizard.TOOLS[t].title, f"tool:{t}")] for t in tools]
    rows.append(_nav_row(back=False))
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
            # Любая команда (/rm, /help…) прерывает пошаговый сценарий:
            # следующее число не должно улететь в забытый шаг.
            msg = getattr(event, "message", None)
            if msg is not None and (msg.text or "").startswith("/"):
                _FLOW.pop(user.id, None)
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
    "<b>Как пользоваться</b>\n"
    "Проще всего — кнопками в меню: бот спросит всё по шагу. "
    "Непонятные слова — в «📖 Объяснение терминов».\n\n"
    "Быстрые команды, если привык:\n"
    "<code>100 8</code> — разовый максимум (вес, повторы)\n"
    "<code>/rpe 140 3 8</code> — максимум по RPE\n"
    "<code>/warmup 140</code> — разминка\n"
    "<code>/dots м 90 500</code>, <code>/wilks ж 62.5 280</code> — пол, вес тела, сумма\n"
    "<code>/rank м 90 500</code> — разряд ЕВСК\n"
    "<code>/ffmi 180 85 15</code> — рост, вес, % жира\n"
    "<code>/kbju м 30 180 85 3 сушка</code> — пол, возраст, рост, вес, активность 1–5, цель\n\n"
    "В любом чате: <code>@{bot} 100 8</code>"
)


def _help_text() -> str:
    return HELP_TEXT.replace("{bot}", BOT_USERNAME or "бот")


@dp.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    # t.me/bot?start=vk_clip1 -> source="vk_clip1": так видно, какой ролик/пост привёл людей
    source = (command.args or "").strip()[:64] or None
    deeplink = wizard.parse_deeplink(source) if source and source.startswith("c-") else None
    if source and source.startswith("c-"):
        source = "webapp"  # кнопка «карточка в чат» из мини-приложения
    if source:
        try:
            storage.touch_user(message.from_user.id, source)
        except Exception:
            logger.exception("Не удалось сохранить источник")
    _log(message.from_user.id, "start")
    _FLOW.pop(message.from_user.id, None)
    if deeplink:
        tool, data = deeplink
        await _send_result(message, tool, data)
        await _send_card(message, message.from_user.id)
        return
    await message.answer(wizard.WELCOME, reply_markup=_main_kb())


@dp.message(Command("menu"))
async def cmd_menu(message: Message):
    _FLOW.pop(message.from_user.id, None)
    await message.answer(wizard.WELCOME, reply_markup=_main_kb())


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(_help_text(), reply_markup=InlineKeyboardMarkup(inline_keyboard=[_nav_row(back=False)]))


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
# Меню и пошаговые сценарии. Одно сообщение бота на сценарий: каждый шаг
# и результат редактируют его, ответы-числа пользователя удаляются.
# ---------------------------------------------------------------------------

async def _edit(bot: Bot, uid: int, chat_id: int, msg_id: int | None, text: str, kb: InlineKeyboardMarkup) -> int:
    """Показать экран в сообщении msg_id; если его нельзя изменить — прислать новое."""
    if msg_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=kb)
            return msg_id
        except TelegramBadRequest as e:
            if "not modified" in str(e):
                return msg_id
    sent = await bot.send_message(chat_id, text, reply_markup=kb)
    return sent.message_id


def _remembered_label(step: wizard.Step, value) -> str:
    if step.key == "sex":
        return "Мужчина" if value == "m" else "Женщина"
    if step.key == "activity":
        return f"активность {value}"
    return f"{num(value)} {step.unit}".strip()


def _step_kb(uid: int, tool: wizard.Tool, i: int) -> InlineKeyboardMarkup:
    step = tool.steps[i]
    rows, row = [], []
    for label, value in step.options:
        row.append(_btn(label, f"ans:{value}"))
        if len(row) == step.columns:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    prev = _LAST_INPUT.get(uid, {}).get(step.remember) if step.remember else None
    if prev is not None:
        value = prev if isinstance(prev, str) else num(prev)
        rows.insert(0, [_btn(f"Как в прошлый раз: {_remembered_label(step, prev)}", f"ans:{value}")])
    rows.append(_nav_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _wizard_result_kb(res: wizard.Result, showing_details: bool = False) -> InlineKeyboardMarkup:
    top = []
    if res.details and not showing_details:
        top.append(_btn(res.details_label, "more"))
    top.append(_btn("Карточка", f"card:{res.kind}"))
    return InlineKeyboardMarkup(inline_keyboard=[
        top,
        [_btn("Посчитать ещё", "again"), _btn("📖 Что это значит?", f"glr:{wizard.section_of(res.kind)}")],
        _nav_row(),
    ])


async def _show_step(bot: Bot, uid: int, error: str | None = None) -> None:
    f = _FLOW[uid]
    tool = wizard.TOOLS[f["tool"]]
    f["msg"] = await _edit(bot, uid, f["chat"], f["msg"], wizard.step_text(tool, f["step"], error),
                           _step_kb(uid, tool, f["step"]))


async def _finish(bot: Bot, uid: int) -> None:
    f = _FLOW[uid]
    try:
        res = wizard.compute(f["tool"], f["data"])
    except ValueError as e:
        f["step"] = 0
        f["data"] = {}
        await _show_step(bot, uid, _fail(str(e)))
        return
    f["step"] = None
    f["result"] = res
    _remember(uid, res.kind, res.render)
    _log(uid, res.kind)
    f["msg"] = await _edit(bot, uid, f["chat"], f["msg"], res.text, _wizard_result_kb(res))


async def _answer(bot: Bot, uid: int, raw: str) -> None:
    f = _FLOW[uid]
    tool = wizard.TOOLS[f["tool"]]
    step = tool.steps[f["step"]]
    try:
        value = wizard.parse(step, raw)
    except ValueError as e:
        await _show_step(bot, uid, str(e))
        return
    f["data"][step.key] = value
    if step.remember:
        _LAST_INPUT.setdefault(uid, {})[step.remember] = value
    f["step"] += 1
    if f["step"] >= len(tool.steps):
        await _finish(bot, uid)
    else:
        await _show_step(bot, uid)


async def _to_menu(bot: Bot, uid: int, chat_id: int, msg_id: int | None) -> None:
    _FLOW.pop(uid, None)
    await _edit(bot, uid, chat_id, msg_id, wizard.WELCOME, _main_kb())


async def _to_section(bot: Bot, uid: int, chat_id: int, msg_id: int | None, section: str) -> None:
    _FLOW.pop(uid, None)
    await _edit(bot, uid, chat_id, msg_id, wizard.section_text(section), _section_kb(section))


@dp.callback_query(F.data == "nav:menu")
async def cb_menu(cb: CallbackQuery):
    await cb.answer()
    await _to_menu(cb.bot, cb.from_user.id, cb.message.chat.id, cb.message.message_id)


@dp.callback_query(F.data.startswith("sec:"))
async def cb_section(cb: CallbackQuery):
    await cb.answer()
    section = cb.data.split(":", 1)[1]
    if section in wizard.SECTIONS:
        await _to_section(cb.bot, cb.from_user.id, cb.message.chat.id, cb.message.message_id, section)


@dp.callback_query(F.data.startswith("tool:"))
async def cb_tool(cb: CallbackQuery):
    await cb.answer()
    key = cb.data.split(":", 1)[1]
    if key not in wizard.TOOLS:
        return
    _FLOW[cb.from_user.id] = {"tool": key, "step": 0, "data": {}, "chat": cb.message.chat.id,
                              "msg": cb.message.message_id, "result": None}
    await _show_step(cb.bot, cb.from_user.id)


@dp.callback_query(F.data.startswith("ans:"))
async def cb_answer(cb: CallbackQuery):
    f = _FLOW.get(cb.from_user.id)
    if not f or f["step"] is None:
        await cb.answer("Это старое меню — начнём заново")
        await _to_menu(cb.bot, cb.from_user.id, cb.message.chat.id, cb.message.message_id)
        return
    await cb.answer()
    f["msg"] = cb.message.message_id
    await _answer(cb.bot, cb.from_user.id, cb.data.split(":", 1)[1])


@dp.callback_query(F.data == "nav:back")
async def cb_back(cb: CallbackQuery):
    await cb.answer()
    uid, chat_id, msg_id = cb.from_user.id, cb.message.chat.id, cb.message.message_id
    f = _FLOW.get(uid)
    if not f:
        await _to_menu(cb.bot, uid, chat_id, msg_id)
        return
    tool = wizard.TOOLS[f["tool"]]
    f["msg"] = msg_id
    if f["step"] is None:          # с результата — к выбору калькулятора
        await _to_section(cb.bot, uid, chat_id, msg_id, tool.section)
    elif f["step"] == 0:
        await _to_section(cb.bot, uid, chat_id, msg_id, tool.section)
    else:
        f["step"] -= 1
        f["data"].pop(tool.steps[f["step"]].key, None)
        await _show_step(cb.bot, uid)


@dp.callback_query(F.data == "again")
async def cb_again(cb: CallbackQuery):
    await cb.answer()
    f = _FLOW.get(cb.from_user.id)
    if not f:
        await _to_menu(cb.bot, cb.from_user.id, cb.message.chat.id, cb.message.message_id)
        return
    f.update(step=0, data={}, result=None, msg=cb.message.message_id)
    await _show_step(cb.bot, cb.from_user.id)


@dp.callback_query(F.data == "more")
async def cb_more(cb: CallbackQuery):
    await cb.answer()
    f = _FLOW.get(cb.from_user.id)
    if not f or not f.get("result") or not f["result"].details:
        return
    res = f["result"]
    f["msg"] = await _edit(cb.bot, cb.from_user.id, cb.message.chat.id, cb.message.message_id,
                           res.details, _wizard_result_kb(res, showing_details=True))


# ---- Объяснение терминов ----

def _glossary_index_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(title, f"gl:{key}")] for key, (title, _) in wizard.SECTIONS.items()
    ] + [[_btn("⬅️ Назад", "nav:menu"), _btn("🏠 Меню", "nav:menu")]])


@dp.callback_query(F.data == "gl")
async def cb_glossary(cb: CallbackQuery):
    await cb.answer()
    _FLOW.pop(cb.from_user.id, None)
    _log(cb.from_user.id, "glossary")
    await _edit(cb.bot, cb.from_user.id, cb.message.chat.id, cb.message.message_id,
                wizard.GLOSSARY_INTRO, _glossary_index_kb())


@dp.callback_query(F.data.startswith("gl:"))
async def cb_glossary_section(cb: CallbackQuery):
    await cb.answer()
    section = cb.data.split(":", 1)[1]
    if section not in wizard.GLOSSARY:
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[_btn("⬅️ Назад", "gl"), _btn("🏠 Меню", "nav:menu")]])
    await _edit(cb.bot, cb.from_user.id, cb.message.chat.id, cb.message.message_id, wizard.GLOSSARY[section], kb)


@dp.callback_query(F.data.startswith("glr:"))
async def cb_glossary_from_result(cb: CallbackQuery):
    """Термины прямо с экрана результата; «Назад» возвращает к цифрам."""
    await cb.answer()
    section = cb.data.split(":", 1)[1]
    if section not in wizard.GLOSSARY:
        return
    _log(cb.from_user.id, "glossary")
    kb = InlineKeyboardMarkup(inline_keyboard=[[_btn("⬅️ К результату", "res"), _btn("🏠 Меню", "nav:menu")]])
    await _edit(cb.bot, cb.from_user.id, cb.message.chat.id, cb.message.message_id, wizard.GLOSSARY[section], kb)


@dp.callback_query(F.data == "res")
async def cb_back_to_result(cb: CallbackQuery):
    f = _FLOW.get(cb.from_user.id)
    if not f or not f.get("result"):
        await cb.answer("Результат устарел — посчитай заново")
        await _to_menu(cb.bot, cb.from_user.id, cb.message.chat.id, cb.message.message_id)
        return
    await cb.answer()
    res = f["result"]
    f["msg"] = await _edit(cb.bot, cb.from_user.id, cb.message.chat.id, cb.message.message_id,
                           res.text, _wizard_result_kb(res))


def _awaiting_text(message: Message) -> bool:
    f = _FLOW.get(message.from_user.id) if message.from_user else None
    return bool(f and f["step"] is not None and message.text and not message.text.startswith("/"))


@dp.message(_awaiting_text)
async def flow_text(message: Message):
    uid = message.from_user.id
    _FLOW[uid]["chat"] = message.chat.id
    try:
        await message.delete()  # ответ-число больше не нужен: экран обновится
    except Exception:  # нет прав или сообщение старое — не страшно
        pass
    await _answer(message.bot, uid, message.text)


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


async def _reply_err(message: Message, text: str) -> None:
    """Ошибка ввода — не тупик: под ней всегда есть выход в меню."""
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[_nav_row(back=False)]))


async def _send_result(message: Message, tool_key: str, data: dict) -> None:
    """Быстрые команды отвечают так же, как пошаговый сценарий: цифра, пояснение, кнопки."""
    try:
        res = wizard.compute(tool_key, data)
    except ValueError as e:
        await _reply_err(message, _fail(str(e)))
        return
    uid = message.from_user.id
    _remember(uid, res.kind, res.render)
    _log(uid, res.kind)
    sent = await message.answer(res.text, reply_markup=_wizard_result_kb(res))
    # Состояние «на экране результата»: работают «Все проценты», «Посчитать ещё», «Назад».
    flow_tool = tool_key if tool_key in wizard.TOOLS else "dots"  # wilks живёт в сценарии DOTS
    _FLOW[uid] = {"tool": flow_tool, "step": None, "data": data, "chat": message.chat.id,
                  "msg": getattr(sent, "message_id", None), "result": res}


async def _send_1rm(message: Message, weight: float, reps_f: float):
    reps = int(round(reps_f))
    if reps >= 37:  # формула Brzycki делит на (37 - повторы)
        await _reply_err(message, _fail("для 37+ повторов разовый максимум не считается"))
        return
    await _send_result(message, "1rm", {"weight": weight, "reps": reps})


@dp.message(Command("rm"))
async def cmd_rm(message: Message):
    args = _args(message)
    if len(args) != 2:
        await _reply_err(message, _usage("/rm 100 8", "вес, повторы"))
        return
    try:
        weight = calc.parse_number(args[0])
        reps = calc.parse_number(args[1])
    except ValueError:
        await _reply_err(message, _fail("не разобрал числа. Пример: /rm 100 8"))
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
        await _reply_err(message, _usage(f"/{kind} м 90 500", "пол, вес тела, сумма"))
        return
    try:
        data = {"sex": _norm_sex(args[0]), "bw": calc.parse_number(args[1]), "total": calc.parse_number(args[2])}
    except ValueError as e:
        await _reply_err(message, _fail(str(e)))
        return
    await _send_result(message, kind, data)


@dp.message(Command("dots"))
async def cmd_dots(message: Message):
    await _strength_score(message, "dots")


@dp.message(Command("wilks"))
async def cmd_wilks(message: Message):
    await _strength_score(message, "wilks")


@dp.message(Command("rank"))
async def cmd_rank(message: Message):
    args = _args(message)
    if len(args) != 3:
        await _reply_err(message, _usage("/rank м 90 500", "пол, вес тела, сумма троеборья"))
        return
    try:
        data = {"sex": _norm_sex(args[0]), "bw": calc.parse_number(args[1]), "total": calc.parse_number(args[2])}
    except ValueError as e:
        await _reply_err(message, _fail(str(e)))
        return
    await _send_result(message, "rank", data)


@dp.message(Command("ffmi"))
async def cmd_ffmi(message: Message):
    args = _args(message)
    if len(args) != 3:
        await _reply_err(message, _usage("/ffmi 180 85 15", "рост в см, вес в кг, % жира"))
        return
    try:
        data = {"height": calc.parse_number(args[0]), "weight": calc.parse_number(args[1]),
                "bf": calc.parse_number(args[2])}
    except ValueError as e:
        await _reply_err(message, _fail(str(e)))
        return
    await _send_result(message, "ffmi", data)


@dp.message(Command("kbju"))
async def cmd_kbju(message: Message):
    args = _args(message)
    if len(args) != 6:
        await _reply_err(message, _usage(
            "/kbju м 30 180 85 3 сушка",
            "пол, возраст, рост, вес, активность 1–5, цель: сушка / поддержание / масса",
        ))
        return
    try:
        goal_raw = args[5].strip().lower()
        if goal_raw not in _GOAL_MAP:
            raise ValueError("цель — сушка, поддержание или масса")
        data = {"sex": _norm_sex(args[0]), "age": int(calc.parse_number(args[1])),
                "height": calc.parse_number(args[2]), "weight": calc.parse_number(args[3]),
                "activity": str(int(calc.parse_number(args[4]))), "goal": _GOAL_MAP[goal_raw]}
    except ValueError as e:
        await _reply_err(message, _fail(str(e)))
        return
    await _send_result(message, "kbju", data)


@dp.message(Command("rpe"))
async def cmd_rpe(message: Message):
    args = _args(message)
    if len(args) != 3:
        await _reply_err(message, _usage("/rpe 140 3 8", "вес, повторы, RPE от 6 до 10"))
        return
    try:
        data = {"weight": calc.parse_number(args[0]), "reps": calc.parse_number(args[1]),
                "rpe": calc.parse_number(args[2])}
    except ValueError as e:
        await _reply_err(message, _fail(str(e)))
        return
    await _send_result(message, "rpe", data)


@dp.message(Command("warmup"))
async def cmd_warmup(message: Message):
    args = _args(message)
    if len(args) not in (1, 2):
        await _reply_err(message, _usage("/warmup 140", "рабочий вес; свой гриф — вторым числом: /warmup 140 15"))
        return
    try:
        data = {"work": calc.parse_number(args[0]),
                "bar": calc.parse_number(args[1]) if len(args) == 2 else 20.0}
    except ValueError as e:
        await _reply_err(message, _fail(str(e)))
        return
    await _send_result(message, "warmup", data)


# ---------------------------------------------------------------------------
# Карточка: фото для превью в чате + по кнопке — файл без сжатия
# ---------------------------------------------------------------------------

def _render(user_id: int):
    data = _LAST_RESULT.get(user_id)
    if not data:
        return None, None
    return data["kind"], data["render"]()


async def _send_card(message: Message, user_id: int) -> bool:
    kind, png = _render(user_id)
    if png is None:
        return False
    _log(user_id, f"card_{kind}")
    # Фото, а не документ: в чате сразу видно картинку, главная цифра читается в превью.
    await message.answer_photo(
        BufferedInputFile(png, filename=f"{kind}.png"),
        caption="Перешли другу — пусть посчитает свой.",
        reply_markup=_card_kb(kind),
    )
    return True


@dp.callback_query(F.data.startswith("card:"))
async def make_card(callback: CallbackQuery):
    if not await _send_card(callback.message, callback.from_user.id):
        await callback.answer("Результат устарел — посчитай заново", show_alert=True)
        return
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
# Всё остальное: непонятный текст — не тупик, а меню
# ---------------------------------------------------------------------------

@dp.message(F.text & ~F.text.startswith("/") & ~F.via_bot)
async def fallback(message: Message):
    await message.answer(
        "Не понял. Выбери калькулятор кнопкой ниже — или напиши вес и повторы, например <code>100 8</code>.",
        reply_markup=_main_kb(),
    )


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
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="rm", description="Разовый максимум: /rm 100 8"),
    BotCommand(command="kbju", description="Калории и БЖУ на день"),
    BotCommand(command="help", description="Как пользоваться и быстрые команды"),
]

BOT_DESCRIPTION = (
    "Считает разовый максимум, рабочие веса, разминку, DOTS и Wilks, разряд ЕВСК, FFMI и КБЖУ. "
    "Пишешь цифры — получаешь математику и карточку для сторис."
)
BOT_SHORT_DESCRIPTION = "Калькулятор зала: максимум, рабочие веса, разряды, КБЖУ."


async def _setup_profile(bot: Bot) -> None:
    """Меню команд, описание и кнопка мини-приложения. Ошибка тут не должна ронять бота."""
    steps = [
        ("команды", bot.set_my_commands(BOT_COMMANDS)),
        ("описание", bot.set_my_description(BOT_DESCRIPTION)),
        ("короткое описание", bot.set_my_short_description(BOT_SHORT_DESCRIPTION)),
    ]
    if WEBAPP_URL:
        steps.append(("кнопка меню", bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Открыть калькулятор", web_app=WebAppInfo(url=WEBAPP_URL)))))
    for name, coro in steps:
        try:
            await coro
        except Exception as e:  # сеть, лимиты Telegram — бот работает и без этого
            logger.warning("Не удалось обновить %s: %s", name, e)


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
    await _setup_profile(bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
