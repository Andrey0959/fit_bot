# -*- coding: utf-8 -*-
"""Проверка контраста цветов дизайн-системы по WCAG 2.1. Запуск: python scripts/check_contrast.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from design import Color  # noqa: E402


def _lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


TEXT_COLORS = ["INK", "TEXT2", "MUTED", "ACCENT", "OK", "WARN", "BAD"]

if __name__ == "__main__":
    ok = True
    for name in TEXT_COLORS:
        c = getattr(Color, name)
        r_bg, r_grid = ratio(c, Color.BG), ratio(c, Color.GRID)
        worst = min(r_bg, r_grid)
        status = "AAA" if worst >= 7 else "AA" if worst >= 4.5 else "FAIL"
        ok &= worst >= 4.5
        print(f"{name:7s} {c}  фон {r_bg:5.2f}  клетка {r_grid:5.2f}  {status}")
    sys.exit(0 if ok else 1)
