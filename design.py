# -*- coding: utf-8 -*-
"""
Дизайн-система «Журнал»: страница тренировочного дневника, записанного ручкой.

Единственное место, где живут цвета, шрифты, размеры и отступы карточек.
cards.py только собирает карточки из примитивов класса Page — никаких
цветов и пикселей по месту.
"""

import io
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Токены
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
FONTS_DIR = ROOT / "fonts"

CHANNEL = "t.me/thirstforfame1"
MSK = timezone(timedelta(hours=3))  # Москва без перехода на летнее время


class Color:
    """Палитра. Контраст текста к фону BG — WCAG AA и выше (см. scripts/check_contrast.py)."""
    BG = "#F2EFE8"           # бумага
    GRID = "#EAE6DC"         # тетрадная клетка — декор, не текст
    INK = "#141414"          # основной текст, жирные линейки       16.0:1
    TEXT2 = "#55534D"        # вторичный текст                        6.7:1
    MUTED = "#615E58"        # подписи, подвал                        5.6:1
    ACCENT = "#2B44D1"       # «синие чернила»: главное и рабочая зона 6.4:1
    RULE = "#D3CDBF"         # тонкие линейки строк
    LEADER = "#BDB6A6"       # точки-лидеры
    SOFT = "#B9B3A5"         # заливка второстепенных сегментов
    OK = "#1A6B40"           # статус «норма»                         5.7:1
    WARN = "#8A4E00"         # статус «внимание»                      5.8:1
    BAD = "#B3262D"          # статус «плохо»                         5.7:1


class Font:
    """Файлы шрифтов (OFL). Цифры и подписи — моноширинный Plex, текст — Inter."""
    MONO = "IBMPlexMono-Regular.ttf"
    MONO_BOLD = "IBMPlexMono-Bold.ttf"
    TEXT = "Inter-Regular.otf"
    TEXT_SEMI = "Inter-SemiBold.otf"


class Size:
    """Кегли в пикселях для карточки 1080×1350."""
    LABEL = 26        # служебные подписи заглавными
    CONTEXT = 34      # строка контекста под цифрой
    ROW = 40          # строки таблиц
    ROW_SMALL = 34    # плотные таблицы (нормативы, расход)
    SCALE = 22        # подписи шкалы
    FOOTER = 24
    HERO_MAX = 250    # главная цифра — подбирается по ширине
    HERO_MIN = 120
    UNIT = 72


class Space:
    """Сетка: всё кратно 8, поля 72, клетка 54."""
    W = 1080
    H = 1350
    MARGIN = 72
    GRID = 54
    HEADER_RULE = 50      # от верхнего поля до жирной линейки шапки
    AFTER_HEADER = 40
    HERO_TOP = 48         # от линейки шапки до верха цифр
    HERO_TO_CONTEXT = 72
    BLOCK = 24            # между блоками
    LINE_CONTEXT = 46     # межстрочный у контекста
    ROW = 66
    ROW_SMALL = 54
    SECTION = 60          # подпись раздела + линейка
    UNDERLINE = 8         # толщина «подчёркнуто ручкой»
    RULE_STRONG = 3
    RULE_SECTION = 2


# ---------------------------------------------------------------------------
# Шрифты
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONTS_DIR / name
    try:
        return ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.BASIC)
    except OSError:
        log.error("Нет шрифта %s — карточка будет некрасивой. Проверь папку fonts/ рядом с design.py", path)
        return ImageFont.load_default()


def today() -> str:
    return datetime.now(MSK).strftime("%d.%m.%Y")


def num(v: float, digits: int = 1) -> str:
    """82.5 -> '82.5', 80.0 -> '80'"""
    s = f"{v:.{digits}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


# ---------------------------------------------------------------------------
# Страница-карточка
# ---------------------------------------------------------------------------

class Page:
    """Одна карточка. Блоки ставятся сверху вниз, курсор self.y двигается сам."""

    def __init__(self, code: str, date: str | None = None):
        S = Space
        self.img = Image.new("RGB", (S.W, S.H), Color.BG)
        self.d = ImageDraw.Draw(self.img)
        self.left = S.MARGIN
        self.right = S.W - S.MARGIN
        self.width = self.right - self.left
        self.code = code
        self._grid()
        self._header(code, date or today())

    # ---- служебное

    def _grid(self):
        for x in range(0, Space.W, Space.GRID):
            self.d.line([x, 0, x, Space.H], fill=Color.GRID, width=1)
        for y in range(0, Space.H, Space.GRID):
            self.d.line([0, y, Space.W, y], fill=Color.GRID, width=1)

    def _text_right(self, y, text, f, fill):
        self.d.text((self.right - self.d.textlength(text, font=f), y), text, font=f, fill=fill)

    def _wrap(self, text: str, f, max_width: float) -> list[str]:
        lines, cur = [], ""
        for word in text.split():
            nxt = f"{cur} {word}".strip()
            if self.d.textlength(nxt, font=f) <= max_width:
                cur = nxt
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def _header(self, code: str, date: str):
        f = font(Font.MONO, Size.LABEL)
        top = Space.MARGIN
        self.d.text((self.left, top), f"ЖУРНАЛ / {code}", font=f, fill=Color.TEXT2)
        self._text_right(top, date, f, Color.TEXT2)
        rule_y = top + Space.HEADER_RULE
        self.d.rectangle([self.left, rule_y, self.right, rule_y + Space.RULE_STRONG - 1], fill=Color.INK)
        self.y = rule_y + Space.AFTER_HEADER

    # ---- блоки

    def hero(self, value: str, unit: str = "", approx: bool = False, underline: bool = True):
        """Главная цифра. approx — оценка: ставим «≈», честно."""
        prefix = "≈" if approx else ""
        f_unit = font(Font.MONO_BOLD, Size.UNIT)
        unit_w = self.d.textlength(unit, font=f_unit) + 16 if unit else 0
        size = Size.HERO_MAX
        while size > Size.HERO_MIN and self.d.textlength(prefix + value, font=font(Font.MONO_BOLD, size)) > self.width - unit_w:
            size -= 6
        f = font(Font.MONO_BOLD, size)
        # ставим по реальной высоте цифр, а не по «воздуху» шрифта над ними
        cap = -f.getbbox("0", anchor="ls")[1]
        base = self.y + Space.HERO_TOP + cap
        x = self.left - 8
        self.d.text((x, base), prefix + value, font=f, fill=Color.INK, anchor="ls")
        end = x + self.d.textlength(prefix + value, font=f)
        if unit:
            self.d.text((end + 14, base), unit, font=f_unit, fill=Color.ACCENT, anchor="ls")
        if underline:
            start = x + self.d.textlength(prefix, font=f)
            uy = base + 28
            self.d.rectangle([start + 4, uy, end - 4, uy + Space.UNDERLINE - 1], fill=Color.ACCENT)
        self.y = base + Space.HERO_TO_CONTEXT

    def context(self, text: str, color: str = Color.TEXT2, semibold: bool = False):
        f = font(Font.TEXT_SEMI if semibold else Font.TEXT, Size.CONTEXT)
        for line in self._wrap(text, f, self.width):
            self.d.text((self.left, self.y), line, font=f, fill=color)
            self.y += Space.LINE_CONTEXT
        self.y += Space.BLOCK

    def section(self, title: str):
        self.y += Space.BLOCK
        self.d.text((self.left, self.y), title.upper(), font=font(Font.MONO, Size.LABEL), fill=Color.TEXT2)
        ry = self.y + 44
        self.d.rectangle([self.left, ry, self.right, ry + Space.RULE_SECTION - 1], fill=Color.INK)
        self.y += Space.SECTION

    def row(self, left: str, right: str, hot: bool = False, small: bool = False,
            marker: str | None = None, dim: bool = False):
        """Строка таблицы: «60% ........ 75 кг». hot — рабочая зона (чернила)."""
        size = Size.ROW_SMALL if small else Size.ROW
        step = Space.ROW_SMALL if small else Space.ROW
        f, fb = font(Font.MONO, size), font(Font.MONO_BOLD, size)
        color = Color.ACCENT if hot else (Color.MUTED if dim else Color.INK)
        self.d.text((self.left, self.y), left, font=f, fill=color)
        x = self.left + self.d.textlength(left, font=f) + 24
        if marker:
            fm = font(Font.MONO, Size.LABEL)
            self.d.text((x, self.y + (size - Size.LABEL) * 0.6), marker, font=fm, fill=Color.ACCENT)
            x += self.d.textlength(marker, font=fm) + 20
        rw = self.d.textlength(right, font=fb)
        dot_y = self.y + size * 0.72
        while x < self.right - rw - 24:
            self.d.ellipse([x, dot_y, x + 4, dot_y + 4], fill=Color.LEADER)
            x += 16
        self.d.text((self.right - rw, self.y), right, font=fb, fill=color)
        self.y += step
        self.d.line([self.left, self.y - 12, self.right, self.y - 12], fill=Color.RULE, width=1)

    def scale(self, value: float, vmin: float, vmax: float, labels: list[str]):
        """Шкала уровня как на миллиметровке: деления, активный отрезок — чернилами."""
        n = len(labels)
        t = max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))
        active = min(n - 1, int(t * n))
        seg = self.width / n
        top = self.y + 26
        self.d.rectangle([self.left, top, self.right, top + 1], fill=Color.INK)
        for i in range(n + 1):
            x = self.left + i * seg
            self.d.line([x, top - 10, x, top + 12], fill=Color.INK, width=2)
        x0 = self.left + active * seg
        self.d.rectangle([x0 + 4, top - 6, x0 + seg - 4, top + 6], fill=Color.ACCENT)
        px = self.left + t * self.width
        self.d.polygon([(px - 11, top - 26), (px + 11, top - 26), (px, top - 10)], fill=Color.ACCENT)
        fl, flb = font(Font.MONO, Size.SCALE), font(Font.MONO_BOLD, Size.SCALE)
        for i, lab in enumerate(labels):
            fx = flb if i == active else fl
            cx = self.left + i * seg + seg / 2
            self.d.text((cx - self.d.textlength(lab, font=fx) / 2, top + 22), lab, font=fx,
                        fill=Color.ACCENT if i == active else Color.MUTED)
        self.y = top + 22 + 40 + Space.BLOCK

    def split_bar(self, parts: list[tuple[str, float, str]]):
        """Полоса долей (например, калории из БЖУ). parts: (подпись, значение, цвет)."""
        total = sum(v for _, v, _ in parts) or 1
        x, top, h = self.left, self.y + 8, 28
        f = font(Font.MONO, Size.SCALE)
        for i, (label, v, col) in enumerate(parts):
            w = self.width * v / total
            self.d.rectangle([x, top, x + w - (4 if i < len(parts) - 1 else 0), top + h], fill=col)
            self.d.text((x, top + h + 10), f"{label} {round(100 * v / total)}%", font=f, fill=Color.MUTED)
            x += w
        self.y = top + h + 10 + 30 + Space.BLOCK

    def footer(self, right: str | None = None, right_color: str = Color.MUTED):
        if self.overflow:
            log.warning("Карточка %s: контент налез на подвал (y=%d)", self.code, self.y)
        f = font(Font.MONO, Size.FOOTER)
        y = Space.H - Space.MARGIN - 24
        self.d.text((self.left, y), CHANNEL, font=f, fill=Color.MUTED)
        if right:
            self._text_right(y, right, f, right_color)

    # ---- результат

    @property
    def overflow(self) -> bool:
        """True, если контент залез на подвал — проверяется в превью."""
        return self.y > Space.H - Space.MARGIN - 48

    def png(self) -> bytes:
        buf = io.BytesIO()
        self.img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
