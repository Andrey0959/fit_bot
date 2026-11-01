# -*- coding: utf-8 -*-
"""
Карточки-результаты в стиле «Журнал» (1080×1350, 4:5 — под чаты, ленту и сторис).
Здесь только состав карточек: цвета, шрифты и отступы берутся из design.py.
"""

from design import Color, Page, num

# Ориентировочные шкалы уровня — для наглядности, не классификация федераций
STRENGTH_SCALE = (100, 600, ["новичок", "любитель", "продвинутый", "элита", "топ"])
FFMI_SCALE = (15, 28, ["низкий", "средний", "хороший", "предел", "выше"])

SEX_LABEL = {"m": "мужчина", "f": "женщина"}


def _reps_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "повтор"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "повтора"
    return "повторов"


def card_1rm(r) -> bytes:
    """r — calculators.OneRMResult"""
    p = Page("1RM")
    p.hero(num(r.average, 0), "кг", approx=True)
    p.context(f"Подход: {num(r.weight)} кг × {r.reps}. Среднее Epley, Brzycki, Lombardi.")
    if not r.reliable:
        p.context("13+ повторов: формулы врут сильнее, бери с запасом.", color=Color.WARN)
    p.section("Рабочие веса")
    for pct, kg in r.table:
        p.row(f"{pct}%", f"{num(kg)} кг", hot=pct >= 85)
    p.footer("85–95% — рабочая зона", Color.ACCENT)
    return p.png()


def card_strength(sex: str, bodyweight: float, total: float, dots: float, wilks: float, main: str = "dots") -> bytes:
    """DOTS и Wilks на одной карточке; main — какой коэффициент главный."""
    code, value = ("DOTS", dots) if main == "dots" else ("WILKS", wilks)
    p = Page(code)
    p.hero(num(value), underline=True)
    p.context(f"{SEX_LABEL[sex].capitalize()} · вес тела {num(bodyweight)} кг · сумма {num(total)} кг")
    p.section("Коэффициенты")
    p.row("DOTS", num(dots), hot=main == "dots")
    p.row("Wilks", num(wilks), hot=main == "wilks")
    p.section("Уровень")
    vmin, vmax, labels = STRENGTH_SCALE
    p.scale(value, vmin, vmax, labels)
    p.footer("шкала ориентировочная")
    return p.png()


def card_ffmi(height: float, weight: float, bodyfat: float, r) -> bytes:
    """r — calculators.FFMIResult"""
    p = Page("FFMI")
    p.hero(num(r.normalized_ffmi))
    p.context(f"Рост {num(height)} см · вес {num(weight)} кг · жир {num(bodyfat)}%")
    p.context(r.verdict.capitalize() + ".", color=Color.INK)
    p.section("Показатели")
    p.row("FFMI норм.", num(r.normalized_ffmi), hot=True)
    p.row("FFMI", num(r.ffmi))
    p.row("Сухая масса", f"{num(r.lean_mass)} кг")
    p.section("Уровень")
    vmin, vmax, labels = FFMI_SCALE
    p.scale(r.normalized_ffmi, vmin, vmax, labels)
    p.footer("точность = точность замера % жира")
    return p.png()


def card_kbju(weight: float, r, note: str | None = None) -> bytes:
    """r — calculators.KbjuResult"""
    p = Page("КБЖУ")
    p.hero(num(r.target_kcal, 0), "ккал")
    p.context(f"{r.goal_label.capitalize()} · вес {num(weight)} кг · {r.activity_label}")
    if note:
        p.context(note, color=Color.WARN)
    p.section("Белки · жиры · углеводы")
    p.split_bar([
        ("белки", r.protein_g * 4, Color.ACCENT),
        ("жиры", r.fat_g * 9, Color.INK),
        ("углеводы", r.carbs_g * 4, Color.SOFT),
    ])
    p.row("Белки", f"{num(r.protein_g, 0)} г", hot=True)
    p.row("Жиры", f"{num(r.fat_g, 0)} г")
    p.row("Углеводы", f"{num(r.carbs_g, 0)} г")
    p.y += 16
    p.context(f"Расход: в покое {num(r.bmr, 0)} ккал, с активностью {num(r.tdee, 0)} ккал.")
    p.footer("Миффлин — Сан Жеор")
    return p.png()


def card_rpe(r) -> bytes:
    """r — calculators.RpeResult"""
    p = Page("RPE")
    p.hero(num(r.estimated_1rm, 0), "кг", approx=True)
    rounded = f" (округлено из {num(r.rpe)})" if r.rpe_used != r.rpe else ""
    p.context(f"Подход: {num(r.weight)} кг × {r.reps} на RPE {num(r.rpe_used)}{rounded}. Оценка разового максимума.")
    p.section(f"Те же {r.reps} {_reps_word(r.reps)} на другом RPE")
    for rpe_value, kg in r.projection:
        mine = rpe_value == r.rpe_used
        p.row(f"RPE {num(rpe_value)}", f"{num(kg)} кг", hot=mine, marker="← твой подход" if mine else None)
    p.footer("таблица RPE (RTS)")
    return p.png()


def card_warmup(work_weight: float, bar: float, steps) -> bytes:
    """steps — список calculators.WarmupStep"""
    p = Page("РАЗМИНКА")
    p.hero(num(work_weight), "кг")
    p.context(f"Рабочий вес · гриф {num(bar)} кг · подходов до рабочего: {max(len(steps) - 1, 0)}")
    p.section("Подходы")
    for s in steps:
        if s.reps:
            p.row(s.label, f"{num(s.weight)} кг × {s.reps}")
        else:
            p.row(s.label, f"{num(s.weight)} кг", hot=True)
    p.footer("округлено до 2.5 кг")
    return p.png()


def card_rank(sex: str, bodyweight: float, total: float, r, ladder: list[tuple[str, float | None]]) -> bytes:
    """r — calculators.RankResult; ladder — нормативы категории: [(разряд, кг или None)]"""
    has_rank = r.rank != "нет разряда"
    p = Page("ЕВСК")
    is_title = r.rank in ("МСМК", "МС", "КМС")
    p.hero(r.rank if has_rank else "—", "" if is_title or not has_rank else "разряд")
    who = "мужчины" if sex == "m" else "женщины"
    status = "" if has_rank else " Ниже III юношеского."
    p.context(f"Сумма {num(total)} кг · {who}, до {r.weight_class} кг · классика.{status}")
    p.section(f"Нормативы категории до {r.weight_class} кг")
    for name, threshold in ladder:
        if threshold is None:
            p.row(name, "—", small=True, dim=True)
        elif name == r.rank:
            p.row(name, f"{num(threshold)} кг", small=True, hot=True, marker="← ты")
        else:
            p.row(name, f"{num(threshold)} кг", small=True, dim=total < threshold and name != r.next_rank)
    if r.next_rank:
        p.footer(f"до {r.next_rank}: +{num(r.gap_to_next)} кг", Color.ACCENT)
    else:
        p.footer("высший разряд категории")
    return p.png()
