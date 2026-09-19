# -*- coding: utf-8 -*-
"""
Генерация карточек-картинок для шаринга в соцсети.
Шрифт лежит прямо в проекте (fonts/) — не зависит от того, что установлено
в системе, поэтому работает одинаково на Linux/macOS/Windows.
"""

import io
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1080

BG_TOP = (20, 20, 23)
BG_BOTTOM = (12, 12, 14)
ACCENT = (214, 255, 64)      # кислотно-салатовый — читается как "спортивный"
WHITE = (245, 245, 245)
GRAY = (150, 150, 155)
LINE = (48, 48, 52)

_HERE = os.path.dirname(os.path.abspath(__file__))
_FONT_BOLD_PATH = os.path.join(_HERE, "fonts", "DejaVuSans-Bold.ttf")
_FONT_REGULAR_PATH = os.path.join(_HERE, "fonts", "DejaVuSans.ttf")


def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    path = _FONT_BOLD_PATH if bold else _FONT_REGULAR_PATH
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    # запасной вариант, если папку fonts/ случайно не скопировали рядом с bot.py —
    # тогда хотя бы латиница/цифры отрисуются, кириллица может выпасть в квадраты
    return ImageFont.load_default()


def _base_card():
    img = Image.new("RGB", (W, H), BG_TOP)
    draw = ImageDraw.Draw(img)
    # вертикальный градиент фона для глубины
    for y in range(H):
        t = y / H
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    # акцентная полоса сверху
    draw.rectangle([0, 0, W, 16], fill=ACCENT)
    return img, draw


def _footer(draw, brand: str):
    f_small = _font(False, 28)
    draw.text((60, H - 68), brand, font=f_small, fill=GRAY)
    # маленькая точка-акцент рядом с брендом
    draw.ellipse([60 - 0, H - 66, 60 - 0, H - 66], fill=ACCENT)


def _hline(draw, y):
    draw.line([(60, y), (W - 60, y)], fill=LINE, width=2)


def card_1rm(weight, reps, average, table, brand="@thirstforfame1") -> bytes:
    img, draw = _base_card()
    f_label = _font(False, 32)
    f_big = _font(True, 140)
    f_unit = _font(True, 46)
    f_row = _font(False, 40)
    f_row_b = _font(True, 40)

    draw.text((60, 84), f"{weight:g} КГ × {reps} ПОВТОР{'' if reps == 1 else ('А' if reps < 5 else 'ОВ')}".upper(),
              font=f_label, fill=GRAY)
    draw.text((58, 130), f"{average:.0f}", font=f_big, fill=WHITE)
    bbox = draw.textbbox((58, 130), f"{average:.0f}", font=f_big)
    draw.text((bbox[2] + 18, 240), "КГ", font=f_unit, fill=ACCENT)
    draw.text((60, 340), "ТВОЙ ОДНОПОВТОРНЫЙ МАКСИМУМ", font=f_label, fill=GRAY)

    y = 410
    _hline(draw, y)
    y += 44
    for pct, w in table:
        # прогресс-полоса под каждый %, чисто декоративно
        bar_w = int(240 * (pct / 95))
        draw.rounded_rectangle([60, y + 10, 60 + bar_w, y + 20], radius=5,
                                fill=ACCENT if pct >= 85 else (90, 95, 40))
        draw.text((320, y), f"{pct}%", font=f_row, fill=GRAY)
        draw.text((430, y), f"{w:g} кг", font=f_row_b, fill=WHITE)
        y += 66

    _footer(draw, brand)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def card_score(score_label, score_value, sub_label, sub_value, brand="@thirstforfame1") -> bytes:
    """Универсальная карточка на одно большое число (DOTS/Wilks/FFMI)."""
    img, draw = _base_card()
    f_label = _font(False, 32)
    f_big = _font(True, 170)
    f_sub_label = _font(False, 32)
    f_sub = _font(False, 38)

    draw.text((60, 100), score_label.upper(), font=f_label, fill=ACCENT)
    draw.text((58, 150), f"{score_value:.1f}", font=f_big, fill=WHITE)

    y = 440
    _hline(draw, y)
    y += 50
    draw.text((60, y), sub_label.upper(), font=f_label, fill=GRAY)
    y += 54
    for line in sub_value.split("\n"):
        # аккуратный перенос длинных строк (например, вывода по FFMI)
        max_chars = 34
        while len(line) > max_chars:
            cut = line.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            draw.text((60, y), line[:cut], font=f_sub, fill=WHITE)
            line = line[cut:].strip()
            y += 48
        draw.text((60, y), line, font=f_sub, fill=WHITE)
        y += 48

    _footer(draw, brand)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def card_kbju(target, protein, fat, carbs, goal_label, brand="@thirstforfame1") -> bytes:
    img, draw = _base_card()
    f_label = _font(False, 32)
    f_big = _font(True, 140)
    f_unit = _font(True, 46)
    f_row = _font(False, 42)
    f_row_b = _font(True, 42)

    draw.text((60, 84), f"КБЖУ · {goal_label}".upper(), font=f_label, fill=GRAY)
    draw.text((58, 130), f"{target:.0f}", font=f_big, fill=WHITE)
    bbox = draw.textbbox((58, 130), f"{target:.0f}", font=f_big)
    draw.text((bbox[2] + 18, 240), "ККАЛ/ДЕНЬ", font=f_unit, fill=ACCENT)

    y = 410
    _hline(draw, y)
    y += 50
    total = protein * 4 + fat * 9 + carbs * 4
    rows = [
        ("Белки", protein, "г", (214, 255, 64)),
        ("Жиры", fat, "г", (255, 170, 90)),
        ("Углеводы", carbs, "г", (110, 190, 255)),
    ]
    for label, val, unit, color in rows:
        draw.rounded_rectangle([60, y + 8, 84, y + 32], radius=6, fill=color)
        draw.text((105, y), label, font=f_row, fill=GRAY)
        draw.text((430, y), f"{val:.0f} {unit}", font=f_row_b, fill=WHITE)
        y += 72

    _footer(draw, brand)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
