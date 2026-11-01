# -*- coding: utf-8 -*-
"""
Эталон для мини-приложения: прогоняет формулы calculators.py на наборе входов
и пишет результаты в tests/fixtures.json. tests/parity.test.mjs считает то же
самое в webapp/calc.js и сверяет.  Запуск из корня: python tests/make_fixtures.py
"""
import json
import random
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import calculators as calc  # noqa: E402

# wizard.py тянет за собой Pillow (карточки) — помощники берём из calculators напрямую.


def plain(x):
    if is_dataclass(x):
        return {k: plain(v) for k, v in asdict(x).items()}
    if isinstance(x, (list, tuple)):
        return [plain(v) for v in x]
    if isinstance(x, float) and x == float("inf"):
        return "inf"
    return x


def run(fn, *args):
    try:
        return {"ok": plain(fn(*args))}
    except (ValueError, KeyError) as e:
        return {"error": str(e)}


rnd = random.Random(20261102)
cases = []


def add(fn, *args):
    cases.append({"fn": fn.__name__, "args": list(args), "out": run(fn, *args)})


# 1RM: обычные, пограничные повторы, «половинки» для округления до блина
for w, r in [(100, 8), (60, 15), (140, 1), (102.5, 5), (50, 36), (80, 12), (80, 13), (0, 5), (100, 0)]:
    add(calc.calc_1rm, w, r)
for _ in range(300):
    add(calc.calc_1rm, round(rnd.uniform(1, 400) * 4) / 4, rnd.randint(1, 36))

for sex in ("m", "f"):
    for bw in (35, 40, 52, 59.5, 90, 150, 151, 210, 230):
        for total in (100, 280, 500, 812.5):
            add(calc.calc_dots, sex, bw, total)
            add(calc.calc_wilks, sex, bw, total)
            add(calc.calc_rank, sex, bw, total)
for _ in range(300):
    sex = rnd.choice("mf")
    bw, total = round(rnd.uniform(35, 200), 1), round(rnd.uniform(50, 1000) * 2) / 2
    add(calc.calc_dots, sex, bw, total)
    add(calc.calc_wilks, sex, bw, total)
    add(calc.calc_rank, sex, bw, total)
add(calc.calc_rank, "x", 90, 500)

for h, w, bf in [(180, 85, 15), (100, 50, 10), (229, 120, 59), (175, 70, 60), (165, 60, 0), (190, 110, 8)]:
    add(calc.calc_ffmi, h, w, bf)
for _ in range(200):
    add(calc.calc_ffmi, round(rnd.uniform(140, 210), 1), round(rnd.uniform(40, 150), 1), round(rnd.uniform(3, 45), 1))

for goal in ("cut", "maintain", "bulk", "bad"):
    for act in (0, 1, 3, 5, 6):
        add(calc.calc_kbju, "m", 30, 180, 85, act, goal)
for _ in range(200):
    add(calc.calc_kbju, rnd.choice("mf"), rnd.randint(11, 99), round(rnd.uniform(140, 210)),
        round(rnd.uniform(40, 150), 1), rnd.randint(1, 5), rnd.choice(["cut", "maintain", "bulk"]))
add(calc.calc_kbju, "m", 10, 180, 85, 3, "cut")

for w, r, rpe in [(140, 3, 8), (140, 3, 8.3), (140, 3, 8.25), (140, 3, 8.75), (100, 10, 5), (100, 11, 8), (100, 1, 11)]:
    add(calc.calc_rpe, w, r, rpe)
for _ in range(200):
    add(calc.calc_rpe, round(rnd.uniform(20, 300) * 2) / 2, rnd.randint(1, 10), rnd.choice([x / 4 for x in range(22, 42)]))

for work, bar in [(140, 20), (140, 15), (20, 20), (25, 20), (60, 20), (300, 20), (0, 20), (100, 0)]:
    add(calc.generate_warmup, work, bar)
for _ in range(200):
    add(calc.generate_warmup, round(rnd.uniform(21, 400) * 4) / 4, rnd.choice([10, 15, 20]))

# Форматирование чисел: f"{v:.Nf}" в Python — ничьи к чётному
nums = [0.25, 0.75, 1.25, 2.5, 3.5, 0.35, 1.005, 82.5, 80.0, 124.649, 17.25, 3177.5, 2.675, 1e-9, 105.0]
nums += [rnd.uniform(0, 4000) for _ in range(500)] + [round(rnd.uniform(0, 500) * 8) / 8 for _ in range(300)]
from design import num  # noqa: E402  (Pillow импортируется, но шрифты не грузятся)
fmt = [{"v": v, "d": d, "out": num(v, d)} for v in nums for d in (0, 1, 2)]
rounds = [{"v": v, "out": round(v)} for v in [0.5, 1.5, 2.5, -2.5, 16.5, 17.5, 3.4999, 41.25 / 2.5, 43.75 / 2.5]]

out = ROOT / "tests" / "fixtures.json"
out.write_text(json.dumps({"cases": cases, "fmt": fmt, "round": rounds}, ensure_ascii=False), encoding="utf-8")
print(f"{len(cases)} расчётов, {len(fmt)} форматов -> {out.relative_to(ROOT)}")
