// Карточка-результат на canvas — перенос design.py (Page) и cards.py.
// 1080×1350, те же цвета, шрифты, кегли и отступы, что у карточек бота.
import { num, repsWord, rankLadder, STRENGTH_SCALE, FFMI_SCALE } from "./calc.js";

export const CHANNEL = "t.me/thirstforfame1";

const Color = {
  BG: "#F2EFE8", GRID: "#EAE6DC", INK: "#141414", TEXT2: "#55534D", MUTED: "#615E58",
  ACCENT: "#2B44D1", RULE: "#D3CDBF", LEADER: "#BDB6A6", SOFT: "#B9B3A5",
  OK: "#1A6B40", WARN: "#8A4E00", BAD: "#B3262D",
};
const Font = { MONO: "PlexMono", MONO_BOLD: "PlexMonoBold", TEXT: "InterCard", TEXT_SEMI: "InterCardSemi" };
const Size = { LABEL: 26, CONTEXT: 34, ROW: 40, ROW_SMALL: 34, SCALE: 22, FOOTER: 24, HERO_MAX: 250, HERO_MIN: 120, UNIT: 72 };
const Space = {
  W: 1080, H: 1350, MARGIN: 72, GRID: 54, HEADER_RULE: 50, AFTER_HEADER: 40, HERO_TOP: 48,
  HERO_TO_CONTEXT: 72, BLOCK: 24, LINE_CONTEXT: 46, ROW: 66, ROW_SMALL: 54, SECTION: 60,
  UNDERLINE: 8, RULE_STRONG: 3, RULE_SECTION: 2,
};

// Шрифты карточки грузятся один раз, отдельно от шрифтов интерфейса.
const FACES = [
  [Font.MONO, "fonts/PlexMono-Regular.woff"],
  [Font.MONO_BOLD, "fonts/PlexMono-Bold.woff"],
  [Font.TEXT, "fonts/Inter-Regular.woff"],
  [Font.TEXT_SEMI, "fonts/Inter-SemiBold.woff"],
];
let fontsReady = null;
export function loadCardFonts() {
  if (!fontsReady) {
    fontsReady = Promise.all(FACES.map(([family, url]) => {
      const face = new FontFace(family, `url(${url})`);
      return face.load().then((f) => document.fonts.add(f)).catch(() => null);
    }));
  }
  return fontsReady;
}

function today() {
  // Москва, UTC+3, без перехода на летнее время — как в боте
  const d = new Date(Date.now() + 3 * 3600 * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getUTCDate())}.${p(d.getUTCMonth() + 1)}.${d.getUTCFullYear()}`;
}

class Page {
  constructor(code) {
    this.canvas = document.createElement("canvas");
    this.canvas.width = Space.W;
    this.canvas.height = Space.H;
    this.d = this.canvas.getContext("2d");
    this.left = Space.MARGIN;
    this.right = Space.W - Space.MARGIN;
    this.width = this.right - this.left;
    this.d.fillStyle = Color.BG;
    this.d.fillRect(0, 0, Space.W, Space.H);
    this._grid();
    this._header(code, today());
  }

  _font(name, size) { this.d.font = `${size}px ${name}`; }
  _len(text, name, size) { this._font(name, size); return this.d.measureText(text).width; }

  /** Текст от верхней точки шрифта (как anchor «la» в Pillow). */
  _text(x, y, text, name, size, fill) {
    this._font(name, size);
    const m = this.d.measureText("Hg");
    const asc = m.fontBoundingBoxAscent ?? size * 0.93;
    this.d.fillStyle = fill;
    this.d.textBaseline = "alphabetic";
    this.d.fillText(text, x, y + asc);
  }

  _textRight(y, text, name, size, fill) { this._text(this.right - this._len(text, name, size), y, text, name, size, fill); }

  _rect(x0, y0, x1, y1, fill) { this.d.fillStyle = fill; this.d.fillRect(x0, y0, x1 - x0 + 1, y1 - y0 + 1); }

  _line(x0, y0, x1, y1, color, width = 1) {
    this.d.strokeStyle = color; this.d.lineWidth = width;
    this.d.beginPath(); this.d.moveTo(x0 + 0.5, y0 + 0.5); this.d.lineTo(x1 + 0.5, y1 + 0.5); this.d.stroke();
  }

  _wrap(text, name, size, maxWidth) {
    const lines = []; let cur = "";
    for (const word of text.split(/\s+/).filter(Boolean)) {
      const nxt = cur ? `${cur} ${word}` : word;
      if (this._len(nxt, name, size) <= maxWidth) cur = nxt;
      else { if (cur) lines.push(cur); cur = word; }
    }
    if (cur) lines.push(cur);
    return lines;
  }

  _grid() {
    for (let x = 0; x < Space.W; x += Space.GRID) this._line(x, 0, x, Space.H, Color.GRID);
    for (let y = 0; y < Space.H; y += Space.GRID) this._line(0, y, Space.W, y, Color.GRID);
  }

  _header(code, date) {
    const top = Space.MARGIN;
    this._text(this.left, top, `ЖУРНАЛ / ${code}`, Font.MONO, Size.LABEL, Color.TEXT2);
    this._textRight(top, date, Font.MONO, Size.LABEL, Color.TEXT2);
    const ry = top + Space.HEADER_RULE;
    this._rect(this.left, ry, this.right, ry + Space.RULE_STRONG - 1, Color.INK);
    this.y = ry + Space.AFTER_HEADER;
  }

  hero(value, unit = "", approx = false, underline = true) {
    const prefix = approx ? "≈" : "";
    const unitW = unit ? this._len(unit, Font.MONO_BOLD, Size.UNIT) + 16 : 0;
    let size = Size.HERO_MAX;
    while (size > Size.HERO_MIN && this._len(prefix + value, Font.MONO_BOLD, size) > this.width - unitW) size -= 6;
    this._font(Font.MONO_BOLD, size);
    const cap = this.d.measureText("0").actualBoundingBoxAscent;
    const base = this.y + Space.HERO_TOP + cap;
    const x = this.left - 8;
    this.d.textBaseline = "alphabetic";
    this.d.fillStyle = Color.INK;
    this.d.fillText(prefix + value, x, base);
    const end = x + this._len(prefix + value, Font.MONO_BOLD, size);
    if (unit) {
      this._font(Font.MONO_BOLD, Size.UNIT);
      this.d.fillStyle = Color.ACCENT;
      this.d.fillText(unit, end + 14, base);
    }
    if (underline) {
      const start = x + this._len(prefix, Font.MONO_BOLD, size);
      const uy = base + 28;
      this._rect(start + 4, uy, end - 4, uy + Space.UNDERLINE - 1, Color.ACCENT);
    }
    this.y = base + Space.HERO_TO_CONTEXT;
  }

  context(text, color = Color.TEXT2, semibold = false) {
    const f = semibold ? Font.TEXT_SEMI : Font.TEXT;
    for (const line of this._wrap(text, f, Size.CONTEXT, this.width)) {
      this._text(this.left, this.y, line, f, Size.CONTEXT, color);
      this.y += Space.LINE_CONTEXT;
    }
    this.y += Space.BLOCK;
  }

  section(title) {
    this.y += Space.BLOCK;
    this._text(this.left, this.y, title.toUpperCase(), Font.MONO, Size.LABEL, Color.TEXT2);
    const ry = this.y + 44;
    this._rect(this.left, ry, this.right, ry + Space.RULE_SECTION - 1, Color.INK);
    this.y += Space.SECTION;
  }

  row(left, right, { hot = false, small = false, marker = null, dim = false } = {}) {
    const size = small ? Size.ROW_SMALL : Size.ROW;
    const step = small ? Space.ROW_SMALL : Space.ROW;
    const color = hot ? Color.ACCENT : dim ? Color.MUTED : Color.INK;
    this._text(this.left, this.y, left, Font.MONO, size, color);
    let x = this.left + this._len(left, Font.MONO, size) + 24;
    if (marker) {
      this._text(x, this.y + (size - Size.LABEL) * 0.6, marker, Font.MONO, Size.LABEL, Color.ACCENT);
      x += this._len(marker, Font.MONO, Size.LABEL) + 20;
    }
    const rw = this._len(right, Font.MONO_BOLD, size);
    const dotY = this.y + size * 0.72;
    this.d.fillStyle = Color.LEADER;
    while (x < this.right - rw - 24) {
      this.d.beginPath(); this.d.arc(x + 2, dotY + 2, 2.5, 0, Math.PI * 2); this.d.fill();
      x += 16;
    }
    this._text(this.right - rw, this.y, right, Font.MONO_BOLD, size, color);
    this.y += step;
    this._line(this.left, this.y - 12, this.right, this.y - 12, Color.RULE);
  }

  scale(value, vmin, vmax, labels) {
    const n = labels.length;
    const t = Math.max(0, Math.min(1, (value - vmin) / (vmax - vmin)));
    const active = Math.min(n - 1, Math.trunc(t * n));
    const seg = this.width / n;
    const top = this.y + 26;
    this._rect(this.left, top, this.right, top + 1, Color.INK);
    for (let i = 0; i <= n; i++) {
      const x = this.left + i * seg;
      this._line(x, top - 10, x, top + 12, Color.INK, 2);
    }
    const x0 = this.left + active * seg;
    this._rect(x0 + 4, top - 6, x0 + seg - 4, top + 6, Color.ACCENT);
    const px = this.left + t * this.width;
    this.d.fillStyle = Color.ACCENT;
    this.d.beginPath(); this.d.moveTo(px - 11, top - 26); this.d.lineTo(px + 11, top - 26); this.d.lineTo(px, top - 10); this.d.fill();
    labels.forEach((lab, i) => {
      const f = i === active ? Font.MONO_BOLD : Font.MONO;
      const cx = this.left + i * seg + seg / 2;
      this._text(cx - this._len(lab, f, Size.SCALE) / 2, top + 22, lab, f, Size.SCALE, i === active ? Color.ACCENT : Color.MUTED);
    });
    this.y = top + 22 + 40 + Space.BLOCK;
  }

  splitBar(parts) {
    const total = parts.reduce((s, [, v]) => s + v, 0) || 1;
    let x = this.left; const top = this.y + 8, h = 28;
    parts.forEach(([label, v, col], i) => {
      const w = (this.width * v) / total;
      this._rect(x, top, x + w - (i < parts.length - 1 ? 4 : 0), top + h, col);
      // round() в Python — к чётному
      const pct = (100 * v) / total;
      const r = Math.abs(pct % 1) === 0.5 ? 2 * Math.round(pct / 2) : Math.round(pct);
      this._text(x, top + h + 10, `${label} ${r}%`, Font.MONO, Size.SCALE, Color.MUTED);
      x += w;
    });
    this.y = top + h + 10 + 30 + Space.BLOCK;
  }

  footer(right = null, rightColor = Color.MUTED) {
    const y = Space.H - Space.MARGIN - 24;
    this._text(this.left, y, CHANNEL, Font.MONO, Size.FOOTER, Color.MUTED);
    if (right) this._textRight(y, right, Font.MONO, Size.FOOTER, rightColor);
  }
}

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const SEX_LABEL = { m: "мужчина", f: "женщина" };

// ---- карточки: состав один в один с cards.py ----

export function card1rm(r) {
  const p = new Page("1RM");
  p.hero(num(r.average, 0), "кг", true);
  p.context(`Подход: ${num(r.weight)} кг × ${r.reps}. Среднее Epley, Brzycki, Lombardi.`);
  if (!r.reliable) p.context("13+ повторов: формулы врут сильнее, бери с запасом.", Color.WARN);
  p.section("Рабочие веса");
  for (const [pct, kg] of r.table) p.row(`${pct}%`, `${num(kg)} кг`, { hot: pct >= 85 });
  p.footer("85–95% — рабочая зона", Color.ACCENT);
  return p.canvas;
}

export function cardStrength(sex, bw, total, dots, wilks, main = "dots") {
  const [code, value] = main === "dots" ? ["DOTS", dots] : ["WILKS", wilks];
  const p = new Page(code);
  p.hero(num(value), "", false, true);
  p.context(`${cap(SEX_LABEL[sex])} · вес тела ${num(bw)} кг · сумма ${num(total)} кг`);
  p.section("Коэффициенты");
  p.row("DOTS", num(dots), { hot: main === "dots" });
  p.row("Wilks", num(wilks), { hot: main === "wilks" });
  p.section("Уровень");
  const [vmin, vmax, labels] = STRENGTH_SCALE;
  p.scale(value, vmin, vmax, labels);
  p.footer("шкала ориентировочная");
  return p.canvas;
}

export function cardFfmi(height, weight, bf, r) {
  const p = new Page("FFMI");
  p.hero(num(r.normalized_ffmi));
  p.context(`Рост ${num(height)} см · вес ${num(weight)} кг · жир ${num(bf)}%`);
  p.context(cap(r.verdict) + ".", Color.INK);
  p.section("Показатели");
  p.row("FFMI норм.", num(r.normalized_ffmi), { hot: true });
  p.row("FFMI", num(r.ffmi));
  p.row("Сухая масса", `${num(r.lean_mass)} кг`);
  p.section("Уровень");
  const [vmin, vmax, labels] = FFMI_SCALE;
  p.scale(r.normalized_ffmi, vmin, vmax, labels);
  p.footer("точность = точность замера % жира");
  return p.canvas;
}

export function cardKbju(weight, r, note) {
  const p = new Page("КБЖУ");
  p.hero(num(r.target_kcal, 0), "ккал");
  p.context(`${cap(r.goal_label)} · вес ${num(weight)} кг · ${r.activity_label}`);
  if (note) p.context(note, Color.WARN);
  p.section("Белки · жиры · углеводы");
  p.splitBar([
    ["белки", r.protein_g * 4, Color.ACCENT],
    ["жиры", r.fat_g * 9, Color.INK],
    ["углеводы", r.carbs_g * 4, Color.SOFT],
  ]);
  p.row("Белки", `${num(r.protein_g, 0)} г`, { hot: true });
  p.row("Жиры", `${num(r.fat_g, 0)} г`);
  p.row("Углеводы", `${num(r.carbs_g, 0)} г`);
  p.y += 16;
  p.context(`Расход: в покое ${num(r.bmr, 0)} ккал, с активностью ${num(r.tdee, 0)} ккал.`);
  p.footer("Миффлин — Сан Жеор");
  return p.canvas;
}

export function cardRpe(r) {
  const p = new Page("RPE");
  p.hero(num(r.estimated_1rm, 0), "кг", true);
  const rounded = r.rpe_used !== r.rpe ? ` (округлено из ${num(r.rpe)})` : "";
  p.context(`Подход: ${num(r.weight)} кг × ${r.reps} на RPE ${num(r.rpe_used)}${rounded}. Оценка разового максимума.`);
  p.section(`Те же ${r.reps} ${repsWord(r.reps)} на другом RPE`);
  for (const [rpe, kg] of r.projection) {
    const mine = rpe === r.rpe_used;
    p.row(`RPE ${num(rpe)}`, `${num(kg)} кг`, { hot: mine, marker: mine ? "← твой подход" : null });
  }
  p.footer("таблица RPE (RTS)");
  return p.canvas;
}

export function cardWarmup(work, bar, steps) {
  const p = new Page("РАЗМИНКА");
  p.hero(num(work), "кг");
  p.context(`Рабочий вес · гриф ${num(bar)} кг · подходов до рабочего: ${Math.max(steps.length - 1, 0)}`);
  p.section("Подходы");
  for (const s of steps) {
    if (s.reps) p.row(s.label, `${num(s.weight)} кг × ${s.reps}`);
    else p.row(s.label, `${num(s.weight)} кг`, { hot: true });
  }
  p.footer("округлено до 2.5 кг");
  return p.canvas;
}

export function cardRank(sex, bw, total, r) {
  const ladder = rankLadder(sex, bw);
  const hasRank = r.rank !== "нет разряда";
  const isTitle = ["МСМК", "МС", "КМС"].includes(r.rank);
  const p = new Page("ЕВСК");
  p.hero(hasRank ? r.rank : "—", isTitle || !hasRank ? "" : "разряд");
  const who = sex === "m" ? "мужчины" : "женщины";
  const status = hasRank ? "" : " Ниже III юношеского.";
  p.context(`Сумма ${num(total)} кг · ${who}, до ${r.weight_class} кг · классика.${status}`);
  p.section(`Нормативы категории до ${r.weight_class} кг`);
  for (const [name, th] of ladder) {
    if (th === null) p.row(name, "—", { small: true, dim: true });
    else if (name === r.rank) p.row(name, `${num(th)} кг`, { small: true, hot: true, marker: "← ты" });
    else p.row(name, `${num(th)} кг`, { small: true, dim: total < th && name !== r.next_rank });
  }
  if (r.next_rank) p.footer(`до ${r.next_rank}: +${num(r.gap_to_next)} кг`, Color.ACCENT);
  else p.footer("высший разряд категории");
  return p.canvas;
}
