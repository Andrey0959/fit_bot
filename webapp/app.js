// Мини-приложение «Калькулятор зала»: экраны, ввод, Telegram WebApp SDK.
// Все расчёты — в calc.js (перенос calculators.py), карточки — в card.js. Сервер не нужен.
import * as C from "./calc.js";
import * as Card from "./card.js";

const BOT = "matematika_zala_bot";
const tg = window.Telegram?.WebApp;
const inTelegram = Boolean(tg && tg.initData);
const can = (v) => inTelegram && tg.isVersionAtLeast?.(v);

// ---------------------------------------------------------------------------
// Калькуляторы: поля и разделы (как в боте, wizard.py)
// ---------------------------------------------------------------------------

const SEX = { key: "sex", q: "Пол", kind: "choice", cols: 2, remember: "sex", options: [["Мужчина", "m"], ["Женщина", "f"]] };
const BW = { key: "bw", q: "Вес тела", lo: 30, hi: 250, example: "82.5", unit: "кг", remember: "bw" };
const WEIGHT = { ...BW, key: "weight", example: "85" };
const HEIGHT = { key: "height", q: "Рост", lo: 100, hi: 230, example: "180", unit: "см", remember: "height" };
const BAR = { key: "weight", q: "Вес на штанге", lo: 1, hi: 500, example: "100", unit: "кг" };
const REPS_10 = Array.from({ length: 10 }, (_, i) => [String(i + 1), String(i + 1)]);

const TOOLS = {
  "1rm": {
    title: "Разовый максимум", code: "1RM", sub: "По подходу на несколько повторов.",
    fields: [BAR, { key: "reps", q: "Повторы", kind: "int", lo: 1, hi: 36, example: "8", quick: REPS_10 }],
  },
  rpe: {
    title: "Максимум по RPE", code: "RPE", sub: "Оценка максимума по тяжести подхода.",
    fields: [BAR, { key: "reps", q: "Повторы", kind: "choice", numeric: true, options: REPS_10 },
      { key: "rpe", q: "RPE", kind: "choice", numeric: true, hint: "10 — отказ, 9 — оставался 1 повтор, 8 — два.",
        options: Array.from({ length: 9 }, (_, i) => [C.num(6 + i / 2), String(6 + i / 2)]) }],
  },
  warmup: {
    title: "Разминка", code: "РАЗМ", sub: "Лестница подходов до рабочего веса.",
    fields: [{ key: "work", q: "Рабочий вес", lo: 21, hi: 500, example: "140", unit: "кг" },
      { key: "bar", q: "Гриф", kind: "choice", numeric: true, cols: 3, remember: "bar", def: "20",
        options: [["20 кг", "20"], ["15 кг", "15"], ["10 кг", "10"]] }],
  },
  dots: {
    title: "DOTS и Wilks", code: "DOTS", sub: "Сила с поправкой на вес тела.",
    fields: [SEX, BW, { key: "total", q: "Сумма троеборья или одно упражнение", lo: 1, hi: 1500, example: "500", unit: "кг" }],
  },
  rank: {
    title: "Разряд ЕВСК", code: "ЕВСК", sub: "Классическое троеборье, без экипировки.",
    fields: [SEX, BW, { key: "total", q: "Сумма: присед + жим + тяга", lo: 1, hi: 1500, example: "500", unit: "кг" }],
  },
  ffmi: {
    title: "FFMI", code: "FFMI", sub: "Индекс сухой массы.",
    fields: [HEIGHT, WEIGHT, { key: "bf", q: "Процент жира", lo: 3, hi: 59, example: "15", unit: "%", remember: "bf",
      hint: "Не мерил — оценка по зеркалу даст погрешность в несколько единиц." }],
  },
  kbju: {
    title: "КБЖУ", code: "ККАЛ", sub: "Калории и БЖУ на день.",
    fields: [SEX, { key: "age", q: "Возраст", kind: "int", lo: 11, hi: 99, example: "30", unit: "лет", remember: "age" },
      HEIGHT, WEIGHT,
      { key: "activity", q: "Активность", kind: "choice", cols: 1, text: true, remember: "activity", options: [
        ["1 — сидячая работа, без спорта", "1"], ["2 — 1–3 тренировки в неделю", "2"],
        ["3 — 3–5 тренировок в неделю", "3"], ["4 — 6–7 тренировок в неделю", "4"],
        ["5 — физический труд + спорт", "5"]] },
      { key: "goal", q: "Цель", kind: "choice", cols: 3, text: true,
        options: [["Сушка", "cut"], ["Поддержание", "maintain"], ["Масса", "bulk"]] }],
  },
};

const SECTIONS = [
  ["Сила", ["1rm", "rpe", "warmup"]],
  ["Пауэрлифтинг", ["dots", "rank"]],
  ["Тело и питание", ["ffmi", "kbju"]],
];

// ---------------------------------------------------------------------------
// Сохранённые ответы: CloudStorage Telegram, вне Telegram — localStorage
// ---------------------------------------------------------------------------

const MEMORY_KEYS = ["sex", "bw", "height", "bf", "age", "activity", "bar"];
let memory = {};

function loadMemory() {
  return new Promise((resolve) => {
    if (can("6.9") && tg.CloudStorage) {
      tg.CloudStorage.getItems(MEMORY_KEYS, (err, values) => {
        if (!err && values) for (const k of MEMORY_KEYS) if (values[k]) memory[k] = values[k];
        resolve();
      });
      setTimeout(resolve, 1500); // не держим интерфейс, если облако молчит
    } else {
      try { memory = JSON.parse(localStorage.getItem("fit_memory") || "{}"); } catch { memory = {}; }
      resolve();
    }
  });
}

function saveMemory(values) {
  for (const [k, v] of Object.entries(values)) {
    if (!MEMORY_KEYS.includes(k)) continue;
    memory[k] = String(v);
    if (can("6.9") && tg.CloudStorage) tg.CloudStorage.setItem(k, String(v), () => {});
  }
  if (!(can("6.9") && tg.CloudStorage)) {
    try { localStorage.setItem("fit_memory", JSON.stringify(memory)); } catch { /* приватный режим */ }
  }
}

// ---------------------------------------------------------------------------
// Telegram: тема, кнопки, вибро
// ---------------------------------------------------------------------------

const haptic = {
  tap: () => can("6.1") && tg.HapticFeedback.selectionChanged(),
  ok: () => can("6.1") && tg.HapticFeedback.notificationOccurred("success"),
  err: () => can("6.1") && tg.HapticFeedback.notificationOccurred("error"),
  soft: () => can("6.1") && tg.HapticFeedback.impactOccurred("light"),
};

function applyTheme() {
  const tp = tg?.themeParams || {};
  let dark = inTelegram ? tg.colorScheme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  if (inTelegram && tp.bg_color) {
    // цвет фона из темы Telegram надёжнее colorScheme на старых клиентах
    const h = tp.bg_color.replace("#", "");
    const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
    dark = 0.2126 * r + 0.7152 * g + 0.0722 * b < 128;
  }
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  const bg = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
  if (can("6.1")) { tg.setHeaderColor(bg); tg.setBackgroundColor(bg); }
  if (can("7.10") && tg.setBottomBarColor) tg.setBottomBarColor(bg);
  mainButton.refresh();
}

/** Одна главная кнопка: нативная MainButton в Telegram, своя внизу экрана в браузере. */
const mainButton = {
  handler: null, text: "", active: true, visible: false,
  set(text, handler, active = true) { Object.assign(this, { text, handler, active, visible: true }); this.refresh(); },
  hide() { this.visible = false; this.refresh(); },
  refresh() {
    const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
    const onAccent = getComputedStyle(document.documentElement).getPropertyValue("--on-accent").trim();
    if (inTelegram) {
      const mb = tg.MainButton;
      if (!this.visible) { mb.hide(); return; }
      mb.setParams({ text: this.text, color: accent, text_color: onAccent, is_active: this.active, is_visible: true });
    } else {
      const dock = document.getElementById("dock");
      const btn = document.getElementById("dockBtn");
      dock.hidden = !this.visible;
      btn.textContent = this.text;
      btn.disabled = !this.active;
    }
  },
  click() { if (this.active && this.handler) this.handler(); },
};

function setBack(show) {
  if (!inTelegram || !can("6.1")) return;
  if (show) tg.BackButton.show(); else tg.BackButton.hide();
}

// ---------------------------------------------------------------------------
// Экраны
// ---------------------------------------------------------------------------

const app = document.getElementById("app");
const crumb = document.getElementById("crumb");
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
let screen = { name: "home" };
let form = {};      // текущие ответы
let errors = {};
let lastResult = null;

function go(next) {
  screen = next;
  render();
  window.scrollTo(0, 0);
}

function back() {
  haptic.soft();
  if (screen.name === "result") go({ name: "tool", tool: screen.tool, keep: true });
  else go({ name: "home" });
}

function render() {
  if (screen.name === "home") renderHome();
  else if (screen.name === "tool") renderTool(screen.tool, screen.keep);
  else if (screen.name === "result") renderResult();
}

function renderHome() {
  crumb.textContent = "ЖУРНАЛ / КАЛЬКУЛЯТОР";
  setBack(false);
  mainButton.hide();
  app.innerHTML = `
    <p class="lead">Считаю разовый максимум, рабочие веса, разминку, DOTS, разряд и КБЖУ. Выбери, что посчитать.</p>
    ${SECTIONS.map(([title, keys]) => `
      <h2 class="label">${title}</h2>
      <ul class="tools">${keys.map((k) => `
        <li><button class="tool" data-tool="${k}">
          <span class="name">${TOOLS[k].title}</span><span class="dots"></span><span class="code">${TOOLS[k].code}</span>
        </button></li>`).join("")}
      </ul>`).join("")}
    <p class="foot">Формулы те же, что в боте <a href="https://t.me/${BOT}">@${BOT}</a>. Данные не уходят с телефона.<br>
    Канал автора: <a href="https://t.me/thirstforfame1">t.me/thirstforfame1</a></p>`;
  app.querySelectorAll("[data-tool]").forEach((b) => b.addEventListener("click", () => {
    haptic.tap();
    go({ name: "tool", tool: b.dataset.tool });
  }));
}

function prefill(tool) {
  const values = {};
  for (const f of TOOLS[tool].fields) {
    if (f.remember && memory[f.remember]) values[f.key] = memory[f.remember];
    else if (f.def) values[f.key] = f.def;
  }
  return values;
}

function fieldHtml(f) {
  const value = form[f.key] ?? "";
  const err = errors[f.key];
  const chips = (opts, cols) => `<div class="chips" style="--cols:${cols}">${opts.map(([label, v]) => `
      <button type="button" class="chip${f.text ? " text" : ""}" data-key="${f.key}" data-value="${esc(v)}"
        aria-pressed="${String(value) === v}">${esc(label)}</button>`).join("")}</div>`;
  if (f.kind === "choice") {
    return `<div class="field${err ? " invalid" : ""}" data-field="${f.key}">
      <span class="q">${f.q}</span>${chips(f.options, f.cols || 5)}
      ${f.hint ? `<p class="hint">${f.hint}</p>` : ""}${err ? `<p class="err">${err}</p>` : ""}</div>`;
  }
  return `<div class="field${err ? " invalid" : ""}" data-field="${f.key}">
    <label for="f_${f.key}">${f.q}</label>
    <div class="input">
      <input id="f_${f.key}" name="${f.key}" inputmode="${f.kind === "int" ? "numeric" : "decimal"}" autocomplete="off"
        enterkeyhint="next" placeholder="${f.example}" value="${esc(value)}">
      ${f.unit ? `<span class="unit">${f.unit}</span>` : ""}
    </div>
    ${f.quick ? chips(f.quick, 5) : ""}
    ${f.hint ? `<p class="hint">${f.hint}</p>` : ""}
    <p class="err">${err || ""}</p></div>`;
}

function renderTool(tool, keep) {
  const t = TOOLS[tool];
  crumb.textContent = `ЖУРНАЛ / ${t.code}`;
  setBack(true);
  if (!keep) { form = prefill(tool); errors = {}; }
  app.innerHTML = `
    <h1>${t.title}</h1><p class="sub">${t.sub}</p>
    <form id="form" novalidate>${t.fields.map(fieldHtml).join("")}</form>
    <button type="button" class="ghost back" id="toMenu">← Все калькуляторы</button>`;
  const inputs = [...app.querySelectorAll("input")];
  inputs.forEach((inp, i) => {
    inp.addEventListener("input", () => {
      form[inp.name] = inp.value;
      if (errors[inp.name]) { errors[inp.name] = null; markField(inp.name); }
      syncChips(inp.name);
      updateMain(tool);
    });
    inp.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      if (inputs[i + 1]) inputs[i + 1].focus(); else { inp.blur(); submit(tool); }
    });
  });
  app.querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => {
    haptic.tap();
    form[b.dataset.key] = b.dataset.value;
    errors[b.dataset.key] = null;
    const inp = app.querySelector(`input[name="${b.dataset.key}"]`);
    if (inp) inp.value = b.dataset.value;
    syncChips(b.dataset.key);
    markField(b.dataset.key);
    updateMain(tool);
  }));
  app.querySelector("#form").addEventListener("submit", (e) => { e.preventDefault(); submit(tool); });
  app.querySelector("#toMenu").addEventListener("click", () => go({ name: "home" }));
  updateMain(tool);
  if (!inTelegram) {
    // в браузере сразу ставим курсор в первое пустое поле
    const empty = inputs.find((i) => !i.value);
    if (empty && matchMedia("(pointer: fine)").matches) empty.focus();
  }
}

function syncChips(key) {
  app.querySelectorAll(`.chip[data-key="${key}"]`).forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.value === String(form[key] ?? ""))));
}

function markField(key) {
  const box = app.querySelector(`[data-field="${key}"]`);
  if (!box) return;
  box.classList.toggle("invalid", Boolean(errors[key]));
  const p = box.querySelector(".err");
  if (p) p.textContent = errors[key] || "";
  else if (errors[key]) box.insertAdjacentHTML("beforeend", `<p class="err">${errors[key]}</p>`);
}

/** Проверка как в боте (wizard.parse): понятный текст без технических слов. */
function parseField(f, raw) {
  if (f.kind === "choice") {
    if (!f.options.some(([, v]) => v === String(raw))) throw new Error("Выбери вариант.");
    return f.numeric ? Number(raw) : String(raw);
  }
  let v;
  try { v = C.parseNumber(raw); } catch { v = NaN; }
  if (!Number.isFinite(v) || v < f.lo || v > f.hi) {
    throw new Error(`Нужно число от ${C.num(f.lo)} до ${C.num(f.hi)}, например ${f.example}.`);
  }
  if (f.kind === "int") {
    if (!Number.isInteger(v)) throw new Error(`Нужно целое число, например ${f.example}.`);
  }
  return v;
}

function filled(tool) {
  return TOOLS[tool].fields.every((f) => form[f.key] !== undefined && String(form[f.key]).trim() !== "");
}

function updateMain(tool) {
  mainButton.set("Посчитать", () => submit(tool), filled(tool));
}

function submit(tool) {
  const t = TOOLS[tool];
  const data = {};
  errors = {};
  for (const f of t.fields) {
    try { data[f.key] = parseField(f, form[f.key] ?? ""); } catch (e) { errors[f.key] = e.message; }
  }
  t.fields.forEach((f) => markField(f.key));
  const firstBad = t.fields.find((f) => errors[f.key]);
  if (firstBad) {
    haptic.err();
    app.querySelector(`[data-field="${firstBad.key}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    return;
  }
  let res;
  try { res = compute(tool, data); } catch (e) {
    haptic.err();
    errors[t.fields[t.fields.length - 1].key] = `Не получилось: ${e.message}`;
    t.fields.forEach((f) => markField(f.key));
    return;
  }
  const remembered = {};
  for (const f of t.fields) if (f.remember) remembered[f.remember] = form[f.key];
  saveMemory(remembered);
  lastResult = { tool, data, ...res };
  haptic.ok();
  go({ name: "result", tool });
}

// ---------------------------------------------------------------------------
// Результаты: те же цифры и тексты, что в боте (wizard.compute)
// ---------------------------------------------------------------------------

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function compute(tool, d) {
  const n = C.num;
  if (tool === "1rm") {
    const r = C.calc1rm(d.weight, d.reps);
    const zone = r.table.filter(([p]) => p >= 85).map(([, w]) => w);
    return {
      hero: [n(r.average), "кг", true],
      lines: [`По подходу ${n(r.weight)} кг × ${r.reps}, среднее трёх формул.`,
        `Рабочая зона 85–95%: ${n(zone[0])}–${n(zone[zone.length - 1])} кг`],
      note: r.reliable ? null : "13+ повторов: оценка грубая, бери с запасом.",
      section: "Рабочие веса",
      rows: r.table.map(([p, w]) => ({ left: `${p}%`, right: `${n(w)} кг`, hot: p >= 85 })),
      extra: `Epley ${n(r.epley)} · Brzycki ${n(r.brzycki)} · Lombardi ${n(r.lombardi)}`,
      card: () => Card.card1rm(r),
    };
  }
  if (tool === "rpe") {
    const r = C.calcRpe(d.weight, d.reps, d.rpe);
    return {
      hero: [n(r.estimated_1rm), "кг", true],
      lines: [`По подходу ${n(r.weight)} кг × ${r.reps} на RPE ${n(r.rpe_used)}.`, "Оценка разового максимума по таблице RTS."],
      section: `Те же ${r.reps} ${C.repsWord(r.reps)} на другом RPE`,
      rows: r.projection.map(([x, w]) => ({ left: `RPE ${n(x)}`, right: `${n(w)} кг`, hot: x === r.rpe_used, mark: x === r.rpe_used ? "← твой подход" : "" })),
      card: () => Card.cardRpe(r),
    };
  }
  if (tool === "warmup") {
    const bar = Number(d.bar);
    const steps = C.generateWarmup(d.work, bar);
    return {
      hero: [n(d.work), "кг", false],
      lines: [`Разминка до рабочего веса. Гриф ${n(bar)} кг, подходов до рабочего: ${Math.max(steps.length - 1, 0)}.`],
      section: "Подходы",
      rows: steps.map((s) => ({ left: s.label, right: s.reps ? `${n(s.weight)} кг × ${s.reps}` : `${n(s.weight)} кг`, hot: !s.reps })),
      card: () => Card.cardWarmup(d.work, bar, steps),
    };
  }
  if (tool === "dots") {
    const dots = C.calcDots(d.sex, d.bw, d.total);
    const wilks = C.calcWilks(d.sex, d.bw, d.total);
    return {
      hero: [n(dots), "DOTS", false],
      lines: [`${d.sex === "m" ? "Мужчина" : "Женщина"}, ${n(d.bw)} кг, сумма ${n(d.total)} кг. Wilks — ${n(wilks)}.`,
        `Уровень: ${C.scaleLabel(dots, C.STRENGTH_SCALE)} (ориентир)`],
      section: "Коэффициенты",
      rows: [{ left: "DOTS", right: n(dots), hot: true }, { left: "Wilks", right: n(wilks) }],
      scale: [dots, C.STRENGTH_SCALE],
      card: () => Card.cardStrength(d.sex, d.bw, d.total, dots, wilks, "dots"),
    };
  }
  if (tool === "rank") {
    const r = C.calcRank(d.sex, d.bw, d.total);
    const has = r.rank !== "нет разряда";
    const ladder = C.rankLadder(d.sex, d.bw);
    return {
      hero: [has ? r.rank : "—", has && !["МСМК", "МС", "КМС"].includes(r.rank) ? "разряд" : "", false],
      lines: [`${has ? "" : "Разряда пока нет. "}Категория до ${r.weight_class} кг, сумма ${n(d.total)} кг, классика.`,
        r.next_rank ? `До ${r.next_rank} — ${n(r.gap_to_next)} кг.` : "Высший разряд категории."],
      section: `Нормативы категории до ${r.weight_class} кг`,
      rows: ladder.map(([name, th]) => th === null
        ? { left: name, right: "—", dim: true }
        : { left: name, right: `${n(th)} кг`, hot: name === r.rank, mark: name === r.rank ? "← ты" : "",
            dim: name !== r.rank && d.total < th && name !== r.next_rank }),
      card: () => Card.cardRank(d.sex, d.bw, d.total, r),
    };
  }
  if (tool === "ffmi") {
    const r = C.calcFfmi(d.height, d.weight, d.bf);
    return {
      hero: [n(r.normalized_ffmi), "FFMI", false],
      lines: [`Сухая масса ${n(r.lean_mass)} кг. ${cap(r.verdict)}.`, "Точность зависит от замера % жира."],
      section: "Показатели",
      rows: [{ left: "FFMI норм.", right: n(r.normalized_ffmi), hot: true }, { left: "FFMI", right: n(r.ffmi) },
        { left: "Сухая масса", right: `${n(r.lean_mass)} кг` }],
      scale: [r.normalized_ffmi, C.FFMI_SCALE],
      card: () => Card.cardFfmi(d.height, d.weight, d.bf, r),
    };
  }
  if (tool === "kbju") {
    const [r, note] = C.kbjuWithGuard(d.sex, d.age, d.height, d.weight, Number(d.activity), d.goal);
    return {
      hero: [n(r.target_kcal, 0), "ккал", false],
      lines: [`В день, ${r.goal_label}.`, `В покое ${n(r.bmr, 0)} ккал, с активностью ${n(r.tdee, 0)} ккал.`],
      note,
      section: "Белки · жиры · углеводы",
      rows: [{ left: "Белки", right: `${n(r.protein_g, 0)} г`, hot: true }, { left: "Жиры", right: `${n(r.fat_g, 0)} г` },
        { left: "Углеводы", right: `${n(r.carbs_g, 0)} г` }],
      card: () => Card.cardKbju(d.weight, r, note),
    };
  }
  throw new Error("неизвестный калькулятор");
}

/** Ссылка «карточка в чат»: бот по /start c-… сам посчитает и пришлёт картинку. */
function deepLink(tool, d) {
  const enc = (v) => String(typeof v === "number" ? +v.toFixed(2) : v).replace(".", "d");
  const order = {
    "1rm": ["weight", "reps"], rpe: ["weight", "reps", "rpe"], warmup: ["work", "bar"],
    dots: ["sex", "bw", "total"], rank: ["sex", "bw", "total"], ffmi: ["height", "weight", "bf"],
    kbju: ["sex", "age", "height", "weight", "activity", "goal"],
  }[tool];
  return `https://t.me/${BOT}?start=c-${tool}-${order.map((k) => enc(d[k])).join("-")}`;
}

let cardBlob = null;
let cardUrl = null;

function renderResult() {
  const r = lastResult;
  const t = TOOLS[r.tool];
  crumb.textContent = `ЖУРНАЛ / ${t.code}`;
  setBack(true);
  const [value, unit, approx] = r.hero;
  const scaleHtml = r.scale ? (() => {
    const [v, [vmin, vmax, labels]] = r.scale;
    const tt = Math.max(0, Math.min(1, (v - vmin) / (vmax - vmin)));
    const active = Math.min(labels.length - 1, Math.trunc(tt * labels.length));
    return `<h2 class="label">Уровень</h2><div class="scale"><span class="ptr" style="left:${(tt * 100).toFixed(1)}%"></span>
      <div class="track">${labels.map((l, i) => `<span class="seg${i === active ? " on" : ""}">${l}</span>`).join("")}</div></div>`;
  })() : "";
  app.innerHTML = `
    <div class="hero"><span class="value">${approx ? '<span class="approx">≈</span>' : ""}${esc(value)}</span>${unit ? `<span class="unit">${unit}</span>` : ""}</div>
    <div class="explain">${r.lines.map((l) => `<p>${esc(l)}</p>`).join("")}${r.note ? `<p class="note">${esc(r.note)}</p>` : ""}</div>
    <h2 class="label">${esc(r.section)}</h2>
    <ul class="rows">${r.rows.map((x) => `<li class="row${x.hot ? " hot" : ""}${x.dim ? " dim" : ""}">
      <span>${esc(x.left)}</span>${x.mark ? `<span class="mark">${x.mark}</span>` : ""}<span class="dots"></span><b>${esc(x.right)}</b></li>`).join("")}</ul>
    ${r.extra ? `<p class="hint">${esc(r.extra)}</p>` : ""}
    ${scaleHtml}
    <div class="cardbox"><h2 class="label">Карточка</h2>
      <p class="hint" id="cardHint">Рисую…</p><img id="cardImg" alt="Карточка с результатом" hidden>
      <div class="actions" id="cardActions"></div></div>
    <div class="actions"><button type="button" class="secondary" id="again">Посчитать ещё</button></div>
    <button type="button" class="ghost back" id="toMenu">← Все калькуляторы</button>`;
  app.querySelector("#again").addEventListener("click", () => { haptic.tap(); go({ name: "tool", tool: r.tool, keep: false }); });
  app.querySelector("#toMenu").addEventListener("click", () => go({ name: "home" }));
  mainButton.hide();
  drawCard(r);
}

async function drawCard(r) {
  await Card.loadCardFonts();
  const canvas = r.card();
  cardBlob = await new Promise((ok) => canvas.toBlob(ok, "image/png"));
  if (cardUrl) URL.revokeObjectURL(cardUrl);
  cardUrl = URL.createObjectURL(cardBlob);
  if (lastResult !== r) return; // пользователь уже ушёл с экрана
  const img = app.querySelector("#cardImg");
  img.src = cardUrl;
  img.hidden = false;

  const file = new File([cardBlob], `${r.tool}.png`, { type: "image/png" });
  const canShare = Boolean(navigator.canShare && navigator.canShare({ files: [file] }));
  const hint = app.querySelector("#cardHint");
  const actions = app.querySelector("#cardActions");
  const buttons = [];
  if (inTelegram) buttons.push(["Прислать карточку в чат", () => { haptic.tap(); tg.openTelegramLink(deepLink(r.tool, r.data)); }]);
  if (canShare) buttons.push(["Поделиться", () => share(file)]);
  buttons.push(["Сохранить PNG", () => download(r.tool)]);
  hint.textContent = inTelegram
    ? (canShare ? "Поделись или пришли её себе в чат с ботом — оттуда легко переслать." : "Бот пришлёт её в чат — оттуда легко переслать или сохранить. Можно и зажать картинку.")
    : "Сохрани или поделись. На телефоне можно зажать картинку.";
  // главное действие — на нативную кнопку, остальные — под картинкой
  const [mainText, mainFn] = buttons[0];
  mainButton.set(mainText, mainFn, true);
  actions.innerHTML = buttons.slice(1).map(([text], i) => `<button type="button" class="secondary" data-i="${i + 1}">${text}</button>`).join("");
  actions.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => buttons[+b.dataset.i][1]()));
}

async function share(file) {
  haptic.tap();
  try {
    await navigator.share({ files: [file], text: `Посчитано в @${BOT}` });
  } catch (e) {
    if (e?.name !== "AbortError") download(lastResult.tool);
  }
}

function download(name) {
  haptic.tap();
  const a = document.createElement("a");
  a.href = cardUrl;
  a.download = `${name}.png`;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

// ---------------------------------------------------------------------------
// Старт
// ---------------------------------------------------------------------------

async function start() {
  const d = new Date(Date.now() + 3 * 3600 * 1000);
  document.getElementById("date").textContent =
    `${String(d.getUTCDate()).padStart(2, "0")}.${String(d.getUTCMonth() + 1).padStart(2, "0")}.${d.getUTCFullYear()}`;
  document.getElementById("dockBtn").addEventListener("click", () => mainButton.click());
  if (inTelegram) {
    tg.ready();
    tg.expand();
    if (can("7.7") && tg.disableVerticalSwipes) tg.disableVerticalSwipes(); // не закрывать свайпом при прокрутке
    tg.MainButton.onClick(() => mainButton.click());
    if (can("6.1")) tg.BackButton.onClick(back);
    tg.onEvent("themeChanged", applyTheme);
  } else {
    matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", applyTheme);
  }
  applyTheme();
  await loadMemory();
  // Открыли с параметром (?tool=kbju или startapp=kbju) — сразу нужный калькулятор
  const startParam = tg?.initDataUnsafe?.start_param || new URLSearchParams(location.search).get("tool");
  if (startParam && TOOLS[startParam]) go({ name: "tool", tool: startParam });
  else go({ name: "home" });
  Card.loadCardFonts(); // заранее, чтобы карточка рисовалась сразу
}

start();
