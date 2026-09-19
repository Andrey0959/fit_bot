# -*- coding: utf-8 -*-
"""
Чистая математика. Никаких зависимостей от Telegram — можно тестировать отдельно.
"""

from dataclasses import dataclass, field
from typing import List


def parse_number(raw: str) -> float:
    """Принимает '82,5' / '82.5' / '82' -> float. Кидает ValueError на мусоре."""
    raw = raw.strip().replace(",", ".")
    return float(raw)


def round_plate(weight: float, step: float = 2.5) -> float:
    """Округление до ближайшего шага блинов (по умолчанию 2.5 кг на сторону = 5 кг на штангу)."""
    return round(weight / step) * step


# ---------------------------------------------------------------------------
# 1RM + процентовка
# ---------------------------------------------------------------------------

@dataclass
class OneRMResult:
    weight: float
    reps: int
    epley: float
    brzycki: float
    lombardi: float
    average: float
    reliable: bool
    table: List[tuple]  # (percent, weight_rounded)


def calc_1rm(weight: float, reps: int) -> OneRMResult:
    if weight <= 0:
        raise ValueError("Вес должен быть больше нуля")
    if reps <= 0:
        raise ValueError("Повторы должны быть больше нуля")

    epley = weight * (1 + reps / 30)
    brzycki = weight * 36 / (37 - reps) if reps < 37 else float("inf")
    lombardi = weight * (reps ** 0.10)
    average = (epley + brzycki + lombardi) / 3

    reliable = reps <= 12  # формулы сильно врут на высоких повторах

    percents = [60, 65, 70, 75, 80, 85, 90, 95]
    table = [(p, round_plate(average * p / 100)) for p in percents]

    return OneRMResult(weight, reps, epley, brzycki, lombardi, average, reliable, table)


# ---------------------------------------------------------------------------
# DOTS
# ---------------------------------------------------------------------------

_DOTS_COEF = {
    "m": (-307.75076, 24.0900756, -0.1918759221, 0.0007391293, -0.000001093),
    "f": (-57.96288, 13.6175032, -0.1126655495, 0.0005158568, -0.0000010706),
}


def calc_dots(sex: str, bodyweight: float, total: float) -> float:
    sex = sex.lower()
    if sex not in ("m", "f"):
        raise ValueError("Пол: м/ж")
    a, b, c, d, e = _DOTS_COEF[sex]
    bw = min(max(bodyweight, 40 if sex == "m" else 40), 210 if sex == "m" else 150)
    denom = a + b * bw + c * bw**2 + d * bw**3 + e * bw**4
    return total * 500 / denom


# ---------------------------------------------------------------------------
# Wilks (классическая формула, 2020 года nет — тут «старый» Уилкс, всё ещё
# самый узнаваемый коэффициент в русскоязычном пауэрлифтинге)
# ---------------------------------------------------------------------------

_WILKS_COEF = {
    "m": (-216.0475144, 16.2606339, -0.002388645, -0.00113732, 7.01863e-06, -1.291e-08),
    "f": (594.31747775582, -27.23842536447, 0.82112226871, -0.00930733913, 4.731582e-05, -9.05459e-08),
}


def calc_wilks(sex: str, bodyweight: float, total: float) -> float:
    sex = sex.lower()
    if sex not in ("m", "f"):
        raise ValueError("Пол: м/ж")
    a, b, c, d, e, f = _WILKS_COEF[sex]
    x = bodyweight
    denom = a + b * x + c * x**2 + d * x**3 + e * x**4 + f * x**5
    return total * 500 / denom


# ---------------------------------------------------------------------------
# FFMI
# ---------------------------------------------------------------------------

@dataclass
class FFMIResult:
    ffmi: float
    normalized_ffmi: float
    lean_mass: float
    verdict: str


def calc_ffmi(height_cm: float, weight_kg: float, bodyfat_pct: float) -> FFMIResult:
    if not (100 < height_cm < 230):
        raise ValueError("Рост в см, разумные пределы 100-230")
    if not (0 <= bodyfat_pct < 60):
        raise ValueError("% жира должен быть от 0 до 60")

    height_m = height_cm / 100
    lean_mass = weight_kg * (1 - bodyfat_pct / 100)
    ffmi = lean_mass / (height_m**2)
    normalized = ffmi + 6.1 * (1.8 - height_m)

    if normalized < 18:
        verdict = "ниже среднего для тренирующегося человека"
    elif normalized < 20:
        verdict = "средний уровень для тренирующегося натурала"
    elif normalized < 22:
        verdict = "хороший результат многолетнего натурального тренинга"
    elif normalized < 25:
        verdict = "близко к натуральному генетическому потолку (~25)"
    else:
        verdict = "выше типичного натурального предела — либо редкая генетика, либо фарм. поддержка"

    return FFMIResult(ffmi, normalized, lean_mass, verdict)


# ---------------------------------------------------------------------------
# Калории и БЖУ (Миффлин-Сан Жеор)
# ---------------------------------------------------------------------------

_ACTIVITY = {
    1: (1.2, "минимум движения / сидячая работа"),
    2: (1.375, "лёгкая активность, 1-3 трен/нед"),
    3: (1.55, "средняя активность, 3-5 трен/нед"),
    4: (1.725, "высокая активность, 6-7 трен/нед"),
    5: (1.9, "очень высокая активность / физ. труд + спорт"),
}

_GOAL = {
    "cut": (-0.20, "сушка"),
    "maintain": (0.0, "поддержание"),
    "bulk": (0.12, "набор массы"),
}


@dataclass
class KbjuResult:
    bmr: float
    tdee: float
    target_kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float
    activity_label: str
    goal_label: str


def calc_kbju(sex: str, age: int, height_cm: float, weight_kg: float,
              activity: int, goal: str) -> KbjuResult:
    sex = sex.lower()
    if sex not in ("m", "f"):
        raise ValueError("Пол: м/ж")
    if activity not in _ACTIVITY:
        raise ValueError("Активность: число от 1 до 5")
    if goal not in _GOAL:
        raise ValueError("Цель: cut/maintain/bulk (сушка/поддержание/масса)")
    if not (10 < age < 100):
        raise ValueError("Возраст в разумных пределах")

    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + (5 if sex == "m" else -161)
    mult, activity_label = _ACTIVITY[activity]
    tdee = bmr * mult
    delta, goal_label = _GOAL[goal]
    target = tdee * (1 + delta)

    # белок и жир от собственного веса, углеводы — остаток калорий
    protein_g = weight_kg * (2.0 if goal == "cut" else 1.8)
    fat_g = weight_kg * (0.8 if goal != "cut" else 0.7)
    kcal_from_pf = protein_g * 4 + fat_g * 9
    carbs_g = max((target - kcal_from_pf) / 4, 0)

    return KbjuResult(bmr, tdee, target, protein_g, fat_g, carbs_g, activity_label, goal_label)


# ---------------------------------------------------------------------------
# RPE (Rate of Perceived Exertion) — таблица % от 1ПМ по повторам и RPE.
# Источник: общепринятая RPE-таблица (Tuchscherer / RTS), используется как
# стандарт в пауэрлифтинге для автоматической регулировки нагрузки.
# ---------------------------------------------------------------------------

# ключ — RPE (6.0 .. 10.0 с шагом 0.5), значение — список % от 1ПМ для 1..10 повторов
_RPE_TABLE = {
    10.0: [1.000, 0.955, 0.922, 0.892, 0.863, 0.837, 0.811, 0.786, 0.762, 0.739],
    9.5:  [0.978, 0.939, 0.907, 0.878, 0.850, 0.825, 0.800, 0.776, 0.752, 0.730],
    9.0:  [0.955, 0.922, 0.892, 0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.717],
    8.5:  [0.939, 0.907, 0.878, 0.850, 0.825, 0.800, 0.776, 0.752, 0.730, 0.707],
    8.0:  [0.922, 0.892, 0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.717, 0.694],
    7.5:  [0.907, 0.878, 0.850, 0.825, 0.800, 0.776, 0.752, 0.730, 0.707, 0.685],
    7.0:  [0.892, 0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.717, 0.694, 0.672],
    6.5:  [0.878, 0.850, 0.825, 0.800, 0.776, 0.752, 0.730, 0.707, 0.685, 0.664],
    6.0:  [0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.717, 0.694, 0.672, 0.650],
}

_RPE_MIN, _RPE_MAX = 6.0, 10.0
_RPE_REPS_MAX = 10


def _snap_rpe(rpe: float) -> float:
    """Округление RPE до ближайшего шага 0.5, с зажимом в границы таблицы."""
    snapped = round(rpe * 2) / 2
    return min(max(snapped, _RPE_MIN), _RPE_MAX)


def _rpe_percent(reps: int, rpe: float) -> float:
    if not (1 <= reps <= _RPE_REPS_MAX):
        raise ValueError(f"RPE-таблица покрывает 1-{_RPE_REPS_MAX} повторов")
    rpe = _snap_rpe(rpe)
    return _RPE_TABLE[rpe][reps - 1]


@dataclass
class RpeResult:
    weight: float
    reps: int
    rpe: float
    rpe_used: float  # после округления до шага 0.5
    estimated_1rm: float
    projection: List[tuple]  # (rpe, вес) для тех же повторов на другие RPE


def calc_rpe(weight: float, reps: int, rpe: float) -> RpeResult:
    if weight <= 0:
        raise ValueError("Вес должен быть больше нуля")
    reps = int(round(reps))
    rpe_used = _snap_rpe(rpe)
    pct = _rpe_percent(reps, rpe_used)
    est_1rm = weight / pct

    projection = []
    for target_rpe in (10.0, 9.0, 8.0, 7.0):
        w = round_plate(est_1rm * _rpe_percent(reps, target_rpe))
        projection.append((target_rpe, w))

    return RpeResult(weight, reps, rpe, rpe_used, est_1rm, projection)


# ---------------------------------------------------------------------------
# Разминка — стандартная лестница от пустого грифа до рабочего веса
# ---------------------------------------------------------------------------

@dataclass
class WarmupStep:
    label: str
    weight: float
    reps: int


def generate_warmup(work_weight: float, bar_weight: float = 20.0) -> List[WarmupStep]:
    if work_weight <= 0:
        raise ValueError("Рабочий вес должен быть больше нуля")
    if bar_weight <= 0:
        raise ValueError("Вес грифа должен быть больше нуля")

    steps: List[WarmupStep] = []

    if work_weight <= bar_weight:
        # рабочий вес не тяжелее грифа — разминка не нужна, только сам подход
        steps.append(WarmupStep("Рабочий", work_weight, 0))
        return steps

    steps.append(WarmupStep("Гриф", bar_weight, 8))

    ladder = [(0.40, 5), (0.60, 3), (0.80, 2), (0.90, 1)]
    for pct, reps in ladder:
        w = round_plate(work_weight * pct)
        # пропускаем ступени легче грифа или почти равные рабочему весу —
        # они не добавляют пользы и только удлиняют разминку
        if w <= bar_weight or w >= work_weight:
            continue
        steps.append(WarmupStep(f"{int(pct * 100)}%", w, reps))

    steps.append(WarmupStep("Рабочий", work_weight, 0))
    return steps
