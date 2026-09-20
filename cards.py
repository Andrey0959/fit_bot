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

BG_TOP = (18, 19, 21)
BG_BOTTOM = (12, 13, 14)
ACCENT = (214, 255, 64)      # единственный яркий цвет на карточке — используется точечно
WHITE = (240, 240, 240)
GRAY = (140, 140, 146)
LINE = (42, 42, 46)
TRACK = (38, 39, 42)         # фон прогресс-полосы (единый для всех, без разноцветицы)

_HERE = os.path.dirname(os.path.abspath(__file__))
_FONT_BOLD_PATH = os.path.join(_HERE, "fonts", "DejaVuSans-Bold.ttf")
_FONT_REGULAR_PATH = os.path.join(_HERE, "fonts", "DejaVuSans.ttf")

if not (os.path.exists(_FONT_BOLD_PATH) and os.path.exists(_FONT_REGULAR_PATH)):
    print(
        "[cards.py] ВНИМАНИЕ: не найдены шрифты по пути "
        f"{os.path.join(_HERE, 'fonts')} — кириллица на карточках отрисуется квадратами. "
        "Проверь, что папка 'fonts' с файлами DejaVuSans.ttf и DejaVuSans-Bold.ttf "
        "лежит рядом с cards.py."
    )


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

    # едва заметный силуэт блинов в углу — чисто текстура, не должна спорить
    # с текстом, поэтому цвет почти сливается с фоном (на 4-6 оттенков светлее)
    plate_color = (BG_TOP[0] + 5, BG_TOP[1] + 5, BG_TOP[2] + 6)
    draw.ellipse([W - 320, H - 420, W + 220, H + 80], outline=plate_color, width=26)
    draw.ellipse([W - 200, H - 300, W + 340, H + 200], outline=plate_color, width=18)

    # акцентная полоса сверху
    draw.rectangle([0, 0, W, 16], fill=ACCENT)
    return img, draw


def _footer(draw, brand: str):
    f_small = _font(False, 28)
    draw.text((60, H - 68), brand, font=f_small, fill=GRAY)


def _hline(draw, y):
    draw.line([(60, y), (W - 60, y)], fill=LINE, width=2)


def _draw_gauge(draw, x, y, width, value, vmin, vmax, labels, f_tick):
    """Сегментированная шкала уровня (новичок → топ) с указателем текущего результата.
    Активный сегмент подсвечивается акцентом, остальные — нейтральный трек."""
    n = len(labels)
    gap = 6
    seg_w = (width - gap * (n - 1)) / n
    track_h = 22

    t = max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))
    active_idx = min(n - 1, int(t * n))

    for i in range(n):
        seg_x0 = x + i * (seg_w + gap)
        seg_x1 = seg_x0 + seg_w
        color = ACCENT if i == active_idx else TRACK
        draw.rounded_rectangle([seg_x0, y, seg_x1, y + track_h], radius=6, fill=color)

    # указатель — маленький треугольник точно над результатом
    px = x + t * width
    draw.polygon([(px - 10, y - 16), (px + 10, y - 16), (px, y - 2)], fill=WHITE)

    for i, label in enumerate(labels):
        seg_x0 = x + i * (seg_w + gap)
        cx = seg_x0 + seg_w / 2
        bbox = draw.textbbox((0, 0), label, font=f_tick)
        tw = bbox[2] - bbox[0]
        color = WHITE if i == active_idx else GRAY
        draw.text((cx - tw / 2, y + track_h + 14), label, font=f_tick, fill=color)


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
    bar_max = 260
    for pct, w in table:
        # единая серая полоса-трек + заливка — без цветового разнобоя,
        # акцентный цвет только у топовых процентов (85%+, рабочие пики)
        draw.rounded_rectangle([60, y + 8, 60 + bar_max, y + 22], radius=7, fill=TRACK)
        bar_w = int(bar_max * (pct / 95))
        fill_color = ACCENT if pct >= 85 else WHITE
        draw.rounded_rectangle([60, y + 8, 60 + bar_w, y + 22], radius=7, fill=fill_color)
        draw.text((350, y), f"{pct}%", font=f_row, fill=GRAY)
        draw.text((460, y), f"{w:g} кг", font=f_row_b, fill=WHITE)
        y += 66

    _footer(draw, brand)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def card_score(score_label, score_value, sub_label, sub_value, brand="@thirstforfame1",
               gauge=None) -> bytes:
    """Универсальная карточка на одно большое число (DOTS/Wilks/FFMI).
    gauge (опционально): dict с ключами min, max, labels — рисует шкалу уровня
    под текстом с указателем текущего результата."""
    img, draw = _base_card()
    f_label = _font(False, 32)
    f_big = _font(True, 170)
    f_sub = _font(False, 38)
    f_tick = _font(False, 24)

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

    if gauge:
        y += 40
        _draw_gauge(
            draw, x=60, y=y, width=W - 120,
            value=score_value, vmin=gauge["min"], vmax=gauge["max"],
            labels=gauge["labels"], f_tick=f_tick,
        )

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
    # единая палитра: акцент только у белков (главный приоритет для тренирующегося),
    # остальное — нейтральный белый маркер, без цветового шума
    rows = [
        ("Белки", protein, "г", ACCENT),
        ("Жиры", fat, "г", WHITE),
        ("Углеводы", carbs, "г", WHITE),
    ]
    for label, val, unit, color in rows:
        draw.rounded_rectangle([60, y + 10, 82, y + 32], radius=5, fill=color)
        draw.text((105, y), label, font=f_row, fill=GRAY)
        draw.text((430, y), f"{val:.0f} {unit}", font=f_row_b, fill=WHITE)
        y += 72

    _footer(draw, brand)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
