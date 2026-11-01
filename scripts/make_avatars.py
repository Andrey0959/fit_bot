# -*- coding: utf-8 -*-
"""
Аватар бота в стиле «Журнал»: 640×640, SVG (контуры глифов, без зависимостей от шрифтов) + PNG.
Запуск из корня проекта: python scripts/make_avatars.py  ->  assets/avatar/
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fontTools.pens.boundsPen import BoundsPen  # noqa: E402
from fontTools.pens.svgPathPen import SVGPathPen  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from design import FONTS_DIR, Color, Font  # noqa: E402

OUT = ROOT / "assets" / "avatar"
SIZE = 640

# (имя, символ, фон, цвет символа, высота символа в долях холста, подчёркивание)
VARIANTS = [
    ("1_approx_ink_on_paper", "≈", Color.BG, Color.ACCENT, 0.40, False),
    ("2_percent_underlined", "%", Color.BG, Color.INK, 0.46, True),
    ("3_approx_paper_on_ink", "≈", Color.ACCENT, Color.BG, 0.40, False),
]


def glyph_path(ch: str):
    font = TTFont(FONTS_DIR / Font.MONO_BOLD)
    gs = font.getGlyphSet()
    name = font.getBestCmap()[ord(ch)]
    bp = BoundsPen(gs)
    gs[name].draw(bp)
    sp = SVGPathPen(gs)
    gs[name].draw(sp)
    return sp.getCommands(), bp.bounds  # bounds: xMin, yMin, xMax, yMax в единицах шрифта


def build(name, ch, bg, fg, height, underline):
    d, (x0, y0, x1, y1) = glyph_path(ch)
    target_h = SIZE * height
    s = target_h / (y1 - y0)
    gw, gh = (x1 - x0) * s, (y1 - y0) * s
    shift_up = 40 if underline else 0
    left = (SIZE - gw) / 2 - x0 * s
    top = (SIZE - gh) / 2 - shift_up
    # в SVG ось Y шрифта направлена вверх — переворачиваем
    tx, ty = left, top + y1 * s
    under = ""
    ux0, ux1, uy = (SIZE - gw) / 2 + 10, (SIZE + gw) / 2 - 10, top + gh + 46
    if underline:
        under = f'<rect x="{ux0:.1f}" y="{uy:.1f}" width="{ux1 - ux0:.1f}" height="22" fill="{Color.ACCENT}"/>'
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" viewBox="0 0 {SIZE} {SIZE}">'
        f'<rect width="{SIZE}" height="{SIZE}" fill="{bg}"/>'
        f'<path d="{d}" fill="{fg}" transform="translate({tx:.2f} {ty:.2f}) scale({s:.5f} {-s:.5f})"/>'
        f"{under}</svg>\n"
    )
    (OUT / f"{name}.svg").write_text(svg, encoding="utf-8")

    # PNG: тот же глиф тем же шрифтом, в той же точке начала координат (×4 для сглаживания)
    k = 4
    upem = TTFont(FONTS_DIR / Font.MONO_BOLD)["head"].unitsPerEm
    f = ImageFont.truetype(str(FONTS_DIR / Font.MONO_BOLD), round(s * upem * k))
    img = Image.new("RGB", (SIZE * k, SIZE * k), bg)
    dr = ImageDraw.Draw(img)
    dr.text((tx * k, ty * k), ch, font=f, fill=fg, anchor="ls")
    if underline:
        dr.rectangle([ux0 * k, uy * k, ux1 * k, (uy + 22) * k], fill=Color.ACCENT)
    img.resize((SIZE, SIZE), Image.LANCZOS).save(OUT / f"{name}.png")


def preview():
    """Как аватар выглядит в списке чатов: кружки 160 и 56 px на светлой и тёмной теме."""
    names = [v[0] for v in VARIANTS]
    sheet = Image.new("RGB", (len(names) * 260 + 40, 520), "#FFFFFF")
    dr = ImageDraw.Draw(sheet)
    dr.rectangle([0, 260, sheet.width, 520], fill="#17212B")
    for i, n in enumerate(names):
        av = Image.open(OUT / f"{n}.png")
        for row, size in ((0, 160), (260, 160)):
            m = Image.new("L", (size, size), 0)
            ImageDraw.Draw(m).ellipse([0, 0, size - 1, size - 1], fill=255)
            sheet.paste(av.resize((size, size), Image.LANCZOS), (40 + i * 260, row + 30), m)
            small = 56
            ms = Image.new("L", (small, small), 0)
            ImageDraw.Draw(ms).ellipse([0, 0, small - 1, small - 1], fill=255)
            sheet.paste(av.resize((small, small), Image.LANCZOS), (40 + i * 260 + 180, row + 130), ms)
    sheet.save(OUT / "_preview.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for v in VARIANTS:
        build(*v)
    preview()
    print("готово:", ", ".join(v[0] for v in VARIANTS))
