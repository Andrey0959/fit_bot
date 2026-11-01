# -*- coding: utf-8 -*-
"""
Пошаговые сценарии бота: экраны, вопросы, проверка ввода и тексты результатов.
Без aiogram — чистая логика, проверяется отдельно. Формулы — только из calculators.py.

Тон: коротко, по делу. Главная цифра — первой строкой, затем 1–2 строки пояснения.
"""

from dataclasses import dataclass, field
from typing import Callable

import calculators as calc
import cards
from design import num

# ---------------------------------------------------------------------------
# Описание шагов
# ---------------------------------------------------------------------------


@dataclass
class Step:
    key: str
    prompt: str
    kind: str = "num"            # num | int | choice
    lo: float = 0
    hi: float = 0
    example: str = ""
    options: list[tuple[str, str]] = field(default_factory=list)  # (подпись, значение)
    columns: int = 5
    typing: bool = True          # можно ли ответить текстом, а не кнопкой
    remember: str | None = None  # ключ для кнопки «как в прошлый раз»
    unit: str = ""


@dataclass
class Tool:
    key: str
    title: str
    section: str
    steps: list[Step]


SEX = Step("sex", "Пол?", kind="choice", options=[("Мужчина", "m"), ("Женщина", "f")], columns=2, remember="sex")
BODYWEIGHT = Step("bw", "Вес тела, кг. Например: <code>82.5</code>", lo=30, hi=250, example="82.5", remember="bw", unit="кг")
TOTAL = Step("total", "Сумма троеборья, кг — присед + жим + тяга. Например: <code>500</code>",
             lo=1, hi=1500, example="500", unit="кг")
HEIGHT = Step("height", "Рост, см. Например: <code>180</code>", lo=100, hi=230, example="180", remember="height", unit="см")
WEIGHT = Step("weight", "Вес тела, кг. Например: <code>85</code>", lo=30, hi=250, example="85", remember="bw", unit="кг")
BAR_WEIGHT = Step("weight", "Вес на штанге, кг. Например: <code>100</code>", lo=1, hi=500, example="100", unit="кг")


def _reps(hi: int) -> Step:
    return Step("reps", "Сколько повторов сделал?", kind="int", lo=1, hi=hi, example="8",
                options=[(str(i), str(i)) for i in range(1, 11)])


TOOLS: dict[str, Tool] = {
    "1rm": Tool("1rm", "Разовый максимум", "strength", [BAR_WEIGHT, _reps(36)]),
    "rpe": Tool("rpe", "Максимум по RPE", "strength", [
        BAR_WEIGHT, _reps(10),
        Step("rpe", "Насколько тяжело было? RPE 10 — отказ, 9 — оставался 1 повтор, 8 — два.",
             lo=6, hi=10, example="8", columns=5,
             options=[(num(x / 2), num(x / 2)) for x in range(12, 21)]),
    ]),
    "warmup": Tool("warmup", "Разминка", "strength", [
        Step("work", "Рабочий вес, кг. Например: <code>140</code>", lo=21, hi=500, example="140", unit="кг"),
        Step("bar", "Вес грифа?", lo=5, hi=30, example="20", columns=3,
             options=[("20 кг", "20"), ("15 кг", "15"), ("10 кг", "10")]),
    ]),
    "dots": Tool("dots", "DOTS и Wilks", "pl", [
        SEX, BODYWEIGHT,
        Step("total", "Сумма троеборья или вес в одном упражнении, кг. Например: <code>500</code>",
             lo=1, hi=1500, example="500", unit="кг"),
    ]),
    "rank": Tool("rank", "Разряд ЕВСК", "pl", [SEX, BODYWEIGHT, TOTAL]),
    "ffmi": Tool("ffmi", "FFMI", "body", [
        HEIGHT, WEIGHT,
        Step("bf", "Процент жира. Например: <code>15</code>\nЕсли не мерил — оценка по зеркалу даст погрешность в несколько единиц.",
             lo=3, hi=59, example="15", remember="bf", unit="%"),
    ]),
    "kbju": Tool("kbju", "КБЖУ", "body", [
        SEX,
        Step("age", "Возраст, лет. Например: <code>30</code>", kind="int", lo=11, hi=99, example="30", remember="age"),
        HEIGHT, WEIGHT,
        Step("activity", "Активность?", kind="choice", columns=1, options=[
            ("1 — сидячая работа, без спорта", "1"),
            ("2 — 1–3 тренировки в неделю", "2"),
            ("3 — 3–5 тренировок в неделю", "3"),
            ("4 — 6–7 тренировок в неделю", "4"),
            ("5 — физический труд + спорт", "5"),
        ], remember="activity"),
        Step("goal", "Цель?", kind="choice", columns=3,
             options=[("Сушка", "cut"), ("Поддержание", "maintain"), ("Масса", "bulk")]),
    ]),
}

SECTIONS: dict[str, tuple[str, list[str]]] = {
    "strength": ("Сила", ["1rm", "rpe", "warmup"]),
    "pl": ("Пауэрлифтинг", ["dots", "rank"]),
    "body": ("Тело и питание", ["ffmi", "kbju"]),
}

SECTION_HINT = {
    "strength": "Максимум, рабочие веса и разминка.",
    "pl": "Сила с поправкой на вес тела и разряды.",
    "body": "Мышечная масса и питание.",
}

# ---------------------------------------------------------------------------
# Тексты экранов
# ---------------------------------------------------------------------------

WELCOME = (
    "<b>Калькулятор зала</b>\n"
    "Считаю разовый максимум, рабочие веса, разминку, DOTS, разряд и КБЖУ.\n"
    "Выбери, что посчитать."
)


def section_text(section: str) -> str:
    title, _ = SECTIONS[section]
    return f"<b>{title}</b>\n{SECTION_HINT[section]}"


def step_text(tool: Tool, i: int, error: str | None = None) -> str:
    head = f"<b>{tool.title} · шаг {i + 1} из {len(tool.steps)}</b>"
    body = tool.steps[i].prompt
    return f"{head}\n{error}\n\n{body}" if error else f"{head}\n{body}"


# ---------------------------------------------------------------------------
# Проверка ввода
# ---------------------------------------------------------------------------

def _range_error(step: Step) -> str:
    return f"Нужно число от {num(step.lo)} до {num(step.hi)}, например <code>{step.example}</code>. Попробуй ещё раз."


def parse(step: Step, raw: str):
    """Ответ текстом или кнопкой -> значение. Ошибка — ValueError с понятным текстом."""
    raw = (raw or "").strip()
    if step.kind == "choice":
        for label, value in step.options:
            if raw in (value, label) or raw.lower() == label.lower():
                return value
        if step.key == "sex":
            low = raw.lower()
            if low in ("м", "муж", "m", "мужчина"):
                return "m"
            if low in ("ж", "жен", "f", "женщина"):
                return "f"
        if step.key == "activity" and raw[:1] in "12345" and raw[:1]:
            return raw[:1]
        raise ValueError("Выбери вариант кнопкой ниже.")
    try:
        value = calc.parse_number(raw.split()[0] if raw else raw)
    except (ValueError, IndexError):
        raise ValueError(_range_error(step))
    if step.kind == "int":
        if value != int(value):
            raise ValueError(f"Нужно целое число, например <code>{step.example}</code>.")
        value = int(value)
    if not step.lo <= value <= step.hi:
        raise ValueError(_range_error(step))
    return value


# Мини-приложение просит карточку ссылкой t.me/<бот>?start=c-1rm-102d5-5:
# точка в числах — «d» (в параметре start разрешены только A-Z a-z 0-9 _ -).
DEEPLINK_ORDER = {
    "1rm": ["weight", "reps"], "rpe": ["weight", "reps", "rpe"], "warmup": ["work", "bar"],
    "dots": ["sex", "bw", "total"], "rank": ["sex", "bw", "total"], "ffmi": ["height", "weight", "bf"],
    "kbju": ["sex", "age", "height", "weight", "activity", "goal"],
}


def parse_deeplink(payload: str):
    """'c-ffmi-180-85-15' -> ('ffmi', {...}) или None, если ссылка битая. Проверка — как у ответов в боте."""
    parts = (payload or "").split("-")
    if len(parts) < 3 or parts[0] != "c" or parts[1] not in DEEPLINK_ORDER:
        return None
    tool, keys = parts[1], DEEPLINK_ORDER[parts[1]]
    if len(parts) - 2 != len(keys):
        return None
    steps = {s.key: s for s in TOOLS[tool].steps}
    data = {}
    try:
        for key, raw in zip(keys, parts[2:]):
            step = steps[key]
            data[key] = parse(step, raw if step.kind == "choice" else raw.replace("d", "."))
    except (ValueError, KeyError):
        return None
    return tool, data


# ---------------------------------------------------------------------------
# Общие помощники (используются и командами, и пошаговыми сценариями)
# ---------------------------------------------------------------------------

def kbju_with_guard(sex: str, age: int, height: float, weight: float, activity: int, goal: str):
    """Миффлин-Сан Жеор выведена на взрослых, а дефицит калорий растущему организму
    без врача давать нельзя — до 18 лет «сушку» не считаем, показываем поддержание."""
    note = None
    if age < 18:
        note = "До 18 лет — грубый ориентир."
        if goal == "cut":
            goal = "maintain"
            note += " Дефицит без врача не считаю: показано поддержание."
    return calc.calc_kbju(sex, age, height, weight, activity, goal), note


def rank_ladder(sex: str, bodyweight: float) -> list[tuple[str, float | None]]:
    table = calc._RANK_TABLE_M if sex == "m" else calc._RANK_TABLE_F
    cats = sorted(table)
    cat = next((c for c in cats if bodyweight <= c), cats[-1])
    return [(name, table[cat][name]) for name in calc._RANK_ORDER]


def scale_label(value: float, scale) -> str:
    vmin, vmax, labels = scale
    t = max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))
    return labels[min(len(labels) - 1, int(t * len(labels)))]


# ---------------------------------------------------------------------------
# Результаты
# ---------------------------------------------------------------------------

@dataclass
class Result:
    kind: str                     # для карточки и аналитики
    text: str                     # короткий результат
    render: Callable[[], bytes]   # рисует карточку
    details: str | None = None    # «Все проценты» и т. п.
    details_label: str | None = None


def compute(tool_key: str, d: dict) -> Result:
    if tool_key == "1rm":
        r = calc.calc_1rm(d["weight"], d["reps"])
        zone = [w for p, w in r.table if p >= 85]
        text = (f"<b>1RM ≈ {num(r.average)} кг</b>\n"
                f"По подходу {num(r.weight)} кг × {r.reps}, среднее трёх формул.\n"
                f"Рабочая зона 85–95%: {num(zone[0])}–{num(zone[-1])} кг")
        if not r.reliable:
            text += "\n13+ повторов: оценка грубая, бери с запасом."
        details = "\n".join([f"<b>1RM ≈ {num(r.average)} кг</b>",
                             f"Epley {num(r.epley)} · Brzycki {num(r.brzycki)} · Lombardi {num(r.lombardi)}", ""]
                            + [f"{p}% — {num(w)} кг" for p, w in r.table])
        return Result("1rm", text, lambda: cards.card_1rm(r), details, "Все проценты")

    if tool_key == "rpe":
        r = calc.calc_rpe(d["weight"], d["reps"], d["rpe"])
        proj = " · ".join(f"RPE {num(x)} — {num(w)}" for x, w in r.projection)
        text = (f"<b>1RM ≈ {num(r.estimated_1rm)} кг</b>\n"
                f"По подходу {num(r.weight)} кг × {r.reps} на RPE {num(r.rpe_used)}.\n"
                f"Те же {r.reps} повт.: {proj} кг")
        if r.rpe_used != r.rpe:
            text += f"\nRPE {num(r.rpe)} округлён до {num(r.rpe_used)}: шаг таблицы 0.5."
        return Result("rpe", text, lambda: cards.card_rpe(r))

    if tool_key == "warmup":
        steps = calc.generate_warmup(d["work"], d["bar"])
        chain = " → ".join(f"{num(s.weight)}×{s.reps}" if s.reps else f"<b>{num(s.weight)}</b>" for s in steps)
        text = (f"<b>Разминка до {num(d['work'])} кг</b>\n"
                f"Гриф {num(d['bar'])} кг, вес × повторы:\n{chain}")
        return Result("warmup", text, lambda: cards.card_warmup(d["work"], d["bar"], steps))

    if tool_key in ("dots", "wilks"):
        dots = calc.calc_dots(d["sex"], d["bw"], d["total"])
        wilks = calc.calc_wilks(d["sex"], d["bw"], d["total"])
        who = "Мужчина" if d["sex"] == "m" else "Женщина"
        main_name, main_val, other_name, other_val = (
            ("DOTS", dots, "Wilks", wilks) if tool_key == "dots" else ("Wilks", wilks, "DOTS", dots))
        text = (f"<b>{main_name} {num(main_val)}</b>\n"
                f"{who}, {num(d['bw'])} кг, сумма {num(d['total'])} кг. {other_name} — {num(other_val)}.\n"
                f"Уровень: {scale_label(main_val, cards.STRENGTH_SCALE)} (ориентир)")
        return Result(tool_key, text,
                      lambda: cards.card_strength(d["sex"], d["bw"], d["total"], dots, wilks, tool_key))

    if tool_key == "rank":
        r = calc.calc_rank(d["sex"], d["bw"], d["total"])
        head = f"<b>Разряд: {r.rank}</b>" if r.rank != "нет разряда" else "<b>Разряда пока нет</b>"
        text = f"{head}\nКатегория до {r.weight_class} кг, сумма {num(d['total'])} кг, классика."
        if r.next_rank:
            text += f"\nДо {r.next_rank} — {num(r.gap_to_next)} кг."
        ladder = rank_ladder(d["sex"], d["bw"])
        return Result("rank", text, lambda: cards.card_rank(d["sex"], d["bw"], d["total"], r, ladder))

    if tool_key == "ffmi":
        r = calc.calc_ffmi(d["height"], d["weight"], d["bf"])
        text = (f"<b>FFMI {num(r.normalized_ffmi)}</b>\n"
                f"Сухая масса {num(r.lean_mass)} кг. {r.verdict.capitalize()}.\n"
                f"Точность зависит от замера % жира.")
        return Result("ffmi", text, lambda: cards.card_ffmi(d["height"], d["weight"], d["bf"], r))

    if tool_key == "kbju":
        r, note = kbju_with_guard(d["sex"], d["age"], d["height"], d["weight"], int(d["activity"]), d["goal"])
        text = (f"<b>{num(r.target_kcal, 0)} ккал в день</b> · {r.goal_label}\n"
                f"Белки {num(r.protein_g, 0)} г · жиры {num(r.fat_g, 0)} г · углеводы {num(r.carbs_g, 0)} г\n"
                f"В покое {num(r.bmr, 0)} ккал, с активностью {num(r.tdee, 0)} ккал.")
        if note:
            text += f"\n{note}"
        return Result("kbju", text, lambda: cards.card_kbju(d["weight"], r, note))

    raise KeyError(tool_key)
