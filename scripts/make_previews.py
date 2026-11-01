# -*- coding: utf-8 -*-
"""
Превью всех карточек на тестовых данных -> previews/*.png и общий лист previews/_all.png.
Запуск из корня проекта: python scripts/make_previews.py
"""
import io
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw  # noqa: E402

import calculators as calc  # noqa: E402
import cards  # noqa: E402
from design import Color, Font, Space, font  # noqa: E402

OUT = ROOT / "previews"


def ladder(sex: str, bodyweight: float):
    table = calc._RANK_TABLE_M if sex == "m" else calc._RANK_TABLE_F
    cats = sorted(table)
    cat = next((c for c in cats if bodyweight <= c), cats[-1])
    return [(name, table[cat][name]) for name in calc._RANK_ORDER]


def build() -> dict[str, bytes]:
    out = {}
    out["1rm"] = cards.card_1rm(calc.calc_1rm(100, 8))
    out["1rm_15reps"] = cards.card_1rm(calc.calc_1rm(60, 15))
    d, w = calc.calc_dots("m", 90, 500), calc.calc_wilks("m", 90, 500)
    out["dots"] = cards.card_strength("m", 90, 500, d, w, "dots")
    out["wilks"] = cards.card_strength("f", 62.5, 280, calc.calc_dots("f", 62.5, 280), calc.calc_wilks("f", 62.5, 280), "wilks")
    out["ffmi"] = cards.card_ffmi(180, 85, 15, calc.calc_ffmi(180, 85, 15))
    out["kbju"] = cards.card_kbju(85, calc.calc_kbju("m", 30, 180, 85, 3, "cut"))
    out["kbju_teen"] = cards.card_kbju(
        70, calc.calc_kbju("m", 16, 175, 70, 3, "maintain"),
        "До 18 лет — грубый ориентир. Дефицит без врача не считаю: показано поддержание.",
    )
    out["rpe"] = cards.card_rpe(calc.calc_rpe(140, 3, 8.3))
    out["warmup"] = cards.card_warmup(140, 20, calc.generate_warmup(140, 20))
    out["rank"] = cards.card_rank("m", 90, 500, calc.calc_rank("m", 90, 500), ladder("m", 90))
    out["rank_none"] = cards.card_rank("f", 60, 100, calc.calc_rank("f", 60, 100), ladder("f", 60))
    out["rank_top"] = cards.card_rank("m", 82, 760, calc.calc_rank("m", 82, 760), ladder("m", 82))
    return out


def contact_sheet(images: dict[str, bytes]) -> Image.Image:
    cols, tw, th, gap = 4, 360, 450, 24
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + gap) + gap, rows * (th + gap + 36) + gap), "#1F2328")
    d = ImageDraw.Draw(sheet)
    for i, (name, png) in enumerate(images.items()):
        x = gap + (i % cols) * (tw + gap)
        y = gap + (i // cols) * (th + gap + 36)
        sheet.paste(Image.open(io.BytesIO(png)).resize((tw, th), Image.LANCZOS), (x, y + 36))
        d.text((x, y + 4), name, font=font(Font.MONO, 22), fill="#C9CDD2")
    return sheet


class _Collect(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    problems = _Collect()
    logging.getLogger("design").addHandler(problems)
    images = build()
    for name, png in images.items():
        (OUT / f"{name}.png").write_bytes(png)
        im = Image.open(io.BytesIO(png))
        assert im.size == (Space.W, Space.H), name
    contact_sheet(images).save(OUT / "_all.png")
    for m in problems.messages:
        print("ПРОБЛЕМА:", m)
    print(f"готово: {len(images)} карточек в {OUT}")
    sys.exit(1 if problems.messages else 0)
