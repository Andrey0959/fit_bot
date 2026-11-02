// Формулы калькуляторов — перенос calculators.py один в один.
// Не менять отдельно от Python: tests/parity.test.mjs сверяет результаты на одних и тех же входах.
// Python round() округляет «к чётному» (банковское округление), JS Math.round — вверх.
// Чтобы цифры совпадали до копейки, ниже свои pyRound и num.

// ---------------------------------------------------------------------------
// Числа
// ---------------------------------------------------------------------------

/** round(x) из Python: ничья (ровно .5) — к чётному. */
export function pyRound(x) {
  if (Math.abs(x % 1) === 0.5) return 2 * Math.round(x / 2);
  return Math.round(x);
}

/** Есть ли у x ровно «ничья» при округлении до digits знаков (x·2^(digits+1) — нечётное целое). */
function isTie(x, digits) {
  const t = x * 2 ** (digits + 1);
  return Number.isInteger(t) && Math.abs(t % 2) === 1;
}

/** f"{v:.{digits}f}" из Python: как toFixed, но ничьи — к чётному. */
export function pyFixed(v, digits) {
  if (!isTie(v, digits)) return v.toFixed(digits);
  const k = 10 ** digits;
  const lo = Math.floor(v * k);
  const n = lo % 2 === 0 ? lo : lo + 1;
  return (n / k).toFixed(digits);
}

/** design.num: 82.5 -> '82.5', 80.0 -> '80' */
export function num(v, digits = 1) {
  const s = pyFixed(v, digits);
  return s.includes(".") ? s.replace(/0+$/, "").replace(/\.$/, "") : s;
}

/** parse_number: '82,5' / '82.5' / '82' -> число. Мусор -> ошибка. */
export function parseNumber(raw) {
  const s = String(raw).trim().replace(",", ".");
  if (!/^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i.test(s)) throw new Error("не число");
  return Number(s);
}

export function roundPlate(weight, step = 2.5) {
  return pyRound(weight / step) * step;
}

// ---------------------------------------------------------------------------
// 1RM + процентовка
// ---------------------------------------------------------------------------

export function calc1rm(weight, reps) {
  if (weight <= 0) throw new Error("Вес должен быть больше нуля");
  if (reps <= 0) throw new Error("Повторы должны быть больше нуля");
  const epley = weight * (1 + reps / 30);
  const brzycki = reps < 37 ? (weight * 36) / (37 - reps) : Infinity;
  const lombardi = weight * reps ** 0.1;
  const average = (epley + brzycki + lombardi) / 3;
  const reliable = reps <= 12;
  const table = [60, 65, 70, 75, 80, 85, 90, 95].map((p) => [p, roundPlate((average * p) / 100)]);
  return { weight, reps, epley, brzycki, lombardi, average, reliable, table };
}

// ---------------------------------------------------------------------------
// DOTS / Wilks
// ---------------------------------------------------------------------------

const DOTS_COEF = {
  m: [-307.75076, 24.0900756, -0.1918759221, 0.0007391293, -0.000001093],
  f: [-57.96288, 13.6175032, -0.1126655495, 0.0005158568, -0.0000010706],
};

function checkSex(sex) {
  sex = String(sex).toLowerCase();
  if (sex !== "m" && sex !== "f") throw new Error("Пол: м/ж");
  return sex;
}

export function calcDots(sex, bodyweight, total) {
  sex = checkSex(sex);
  const [a, b, c, d, e] = DOTS_COEF[sex];
  const bw = Math.min(Math.max(bodyweight, 40), sex === "m" ? 210 : 150);
  const denom = a + b * bw + c * bw ** 2 + d * bw ** 3 + e * bw ** 4;
  return (total * 500) / denom;
}

const WILKS_COEF = {
  m: [-216.0475144, 16.2606339, -0.002388645, -0.00113732, 7.01863e-6, -1.291e-8],
  f: [594.31747775582, -27.23842536447, 0.82112226871, -0.00930733913, 4.731582e-5, -9.05459e-8],
};

export function calcWilks(sex, bodyweight, total) {
  sex = checkSex(sex);
  const [a, b, c, d, e, f] = WILKS_COEF[sex];
  const x = bodyweight;
  const denom = a + b * x + c * x ** 2 + d * x ** 3 + e * x ** 4 + f * x ** 5;
  return (total * 500) / denom;
}

// ---------------------------------------------------------------------------
// FFMI
// ---------------------------------------------------------------------------

export function calcFfmi(heightCm, weightKg, bodyfatPct) {
  if (!(heightCm > 100 && heightCm < 230)) throw new Error("Рост в см, разумные пределы 100-230");
  if (!(bodyfatPct >= 0 && bodyfatPct < 60)) throw new Error("% жира должен быть от 0 до 60");
  const heightM = heightCm / 100;
  const leanMass = weightKg * (1 - bodyfatPct / 100);
  const ffmi = leanMass / heightM ** 2;
  const normalized = ffmi + 6.1 * (1.8 - heightM);
  let verdict;
  if (normalized < 18) verdict = "ниже среднего для тренирующегося человека";
  else if (normalized < 20) verdict = "средний уровень для тренирующегося натурала";
  else if (normalized < 22) verdict = "хороший результат многолетнего натурального тренинга";
  else if (normalized < 25) verdict = "близко к натуральному генетическому потолку (~25)";
  else verdict = "выше типичного натурального предела — либо редкая генетика, либо фарм. поддержка";
  return { ffmi, normalized_ffmi: normalized, lean_mass: leanMass, verdict };
}

// ---------------------------------------------------------------------------
// Калории и БЖУ (Миффлин — Сан Жеор)
// ---------------------------------------------------------------------------

export const ACTIVITY = {
  1: [1.2, "минимум движения / сидячая работа"],
  2: [1.375, "лёгкая активность, 1-3 трен/нед"],
  3: [1.55, "средняя активность, 3-5 трен/нед"],
  4: [1.725, "высокая активность, 6-7 трен/нед"],
  5: [1.9, "очень высокая активность / физ. труд + спорт"],
};

const GOAL = {
  cut: [-0.2, "сушка"],
  maintain: [0.0, "поддержание"],
  bulk: [0.12, "набор массы"],
};

export function calcKbju(sex, age, heightCm, weightKg, activity, goal) {
  sex = checkSex(sex);
  if (!Number.isInteger(activity) || !(activity in ACTIVITY)) throw new Error("Активность: число от 1 до 5");
  if (!(goal in GOAL)) throw new Error("Цель: cut/maintain/bulk (сушка/поддержание/масса)");
  if (!(age > 10 && age < 100)) throw new Error("Возраст в разумных пределах");
  const bmr = 10 * weightKg + 6.25 * heightCm - 5 * age + (sex === "m" ? 5 : -161);
  const [mult, activityLabel] = ACTIVITY[activity];
  const tdee = bmr * mult;
  const [delta, goalLabel] = GOAL[goal];
  const target = tdee * (1 + delta);
  const protein = weightKg * (goal === "cut" ? 2.0 : 1.8);
  const fat = weightKg * (goal !== "cut" ? 0.8 : 0.7);
  const kcalFromPf = protein * 4 + fat * 9;
  const carbs = Math.max((target - kcalFromPf) / 4, 0);
  return {
    bmr, tdee, target_kcal: target, protein_g: protein, fat_g: fat, carbs_g: carbs,
    activity_label: activityLabel, goal_label: goalLabel,
  };
}

// ---------------------------------------------------------------------------
// RPE — таблица % от 1ПМ (RTS)
// ---------------------------------------------------------------------------

const RPE_TABLE = {
  "10": [1.0, 0.955, 0.922, 0.892, 0.863, 0.837, 0.811, 0.786, 0.762, 0.739],
  "9.5": [0.978, 0.939, 0.907, 0.878, 0.85, 0.825, 0.8, 0.776, 0.752, 0.73],
  "9": [0.955, 0.922, 0.892, 0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.717],
  "8.5": [0.939, 0.907, 0.878, 0.85, 0.825, 0.8, 0.776, 0.752, 0.73, 0.707],
  "8": [0.922, 0.892, 0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.717, 0.694],
  "7.5": [0.907, 0.878, 0.85, 0.825, 0.8, 0.776, 0.752, 0.73, 0.707, 0.685],
  "7": [0.892, 0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.717, 0.694, 0.672],
  "6.5": [0.878, 0.85, 0.825, 0.8, 0.776, 0.752, 0.73, 0.707, 0.685, 0.664],
  "6": [0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.717, 0.694, 0.672, 0.65],
};
const RPE_MIN = 6.0, RPE_MAX = 10.0, RPE_REPS_MAX = 10;

function snapRpe(rpe) {
  const snapped = pyRound(rpe * 2) / 2;
  return Math.min(Math.max(snapped, RPE_MIN), RPE_MAX);
}

function rpePercent(reps, rpe) {
  if (!(reps >= 1 && reps <= RPE_REPS_MAX)) throw new Error(`RPE-таблица покрывает 1-${RPE_REPS_MAX} повторов`);
  return RPE_TABLE[String(snapRpe(rpe))][reps - 1];
}

export function calcRpe(weight, reps, rpe) {
  if (weight <= 0) throw new Error("Вес должен быть больше нуля");
  reps = pyRound(reps);
  const rpeUsed = snapRpe(rpe);
  const est = weight / rpePercent(reps, rpeUsed);
  const projection = [10.0, 9.0, 8.0, 7.0].map((t) => [t, roundPlate(est * rpePercent(reps, t))]);
  return { weight, reps, rpe, rpe_used: rpeUsed, estimated_1rm: est, projection };
}

// ---------------------------------------------------------------------------
// Разминка
// ---------------------------------------------------------------------------

export function generateWarmup(workWeight, barWeight = 20.0) {
  if (workWeight <= 0) throw new Error("Рабочий вес должен быть больше нуля");
  if (barWeight <= 0) throw new Error("Вес грифа должен быть больше нуля");
  const steps = [];
  if (workWeight <= barWeight) {
    steps.push({ label: "Рабочий", weight: workWeight, reps: 0 });
    return steps;
  }
  steps.push({ label: "Гриф", weight: barWeight, reps: 8 });
  for (const [pct, reps] of [[0.4, 5], [0.6, 3], [0.8, 2], [0.9, 1]]) {
    const w = roundPlate(workWeight * pct);
    if (w <= barWeight || w >= workWeight) continue;
    steps.push({ label: `${Math.trunc(pct * 100)}%`, weight: w, reps });
  }
  steps.push({ label: "Рабочий", weight: workWeight, reps: 0 });
  return steps;
}

// ---------------------------------------------------------------------------
// Разряды ЕВСК — классика (приказ Минспорта № 1255 с изм. 2023–2024)
// ---------------------------------------------------------------------------

export const RANK_ORDER = ["МСМК", "МС", "КМС", "I", "II", "III", "I(ю)", "II(ю)", "III(ю)"];

const row = (a) => Object.fromEntries(RANK_ORDER.map((r, i) => [r, a[i]]));
const RANK_TABLE_M = {
  53: row([null, null, 340.0, 300.0, 265.0, 240.0, 215.0, 200.0, 185.0]),
  59: row([545.0, 465.0, 385.0, 340.0, 300.0, 275.0, 245.0, 225.0, 205.0]),
  66: row([620.0, 525.0, 425.0, 380.0, 335.0, 305.0, 270.0, 245.0, 215.0]),
  74: row([685.0, 580.0, 460.0, 415.0, 365.0, 325.0, 295.0, 260.0, 230.0]),
  83: row([750.0, 640.0, 500.0, 455.0, 400.0, 350.0, 320.0, 290.0, 255.0]),
  93: row([785.0, 690.0, 540.0, 480.0, 430.0, 385.0, 345.0, 315.0, 275.0]),
  105: row([822.5, 720.0, 585.0, 510.0, 460.0, 415.0, 370.0, 330.0, 300.0]),
  120: row([855.0, 770.0, 635.0, 555.0, 505.0, 455.0, 395.0, 355.0, 325.0]),
  999: row([925.0, 815.0, 690.0, 585.0, 525.0, 485.0, 425.0, 370.0, 345.0]),
};
const RANK_TABLE_F = {
  43: row([null, null, 170.0, 145.0, 125.0, 115.0, 105.0, 97.5, 90.0]),
  47: row([335.0, 270.0, 210.0, 170.0, 145.0, 125.0, 115.0, 105.0, 97.5]),
  52: row([370.0, 300.0, 245.0, 195.0, 170.0, 145.0, 125.0, 115.0, 105.0]),
  57: row([390.0, 325.0, 275.0, 205.0, 185.0, 165.0, 145.0, 125.0, 115.0]),
  63: row([422.5, 350.0, 305.0, 230.0, 200.0, 180.0, 160.0, 140.0, 125.0]),
  69: row([440.0, 365.0, 320.0, 252.5, 222.5, 190.0, 170.0, 150.0, 137.5]),
  76: row([457.5, 385.0, 340.0, 277.5, 242.5, 210.0, 190.0, 170.0, 150.0]),
  84: row([475.0, 395.0, 350.0, 295.0, 255.0, 220.0, 200.0, 180.0, 160.0]),
  999: row([525.0, 420.0, 375.0, 317.5, 285.0, 250.0, 220.0, 200.0, 180.0]),
};

function rankCategory(table, bodyweight) {
  const cats = Object.keys(table).map(Number).sort((a, b) => a - b);
  return [cats, cats.find((c) => bodyweight <= c) ?? cats[cats.length - 1]];
}

export function calcRank(sex, bodyweight, total) {
  sex = checkSex(sex);
  if (bodyweight <= 0 || total <= 0) throw new Error("Вес и сумма должны быть больше нуля");
  const table = sex === "m" ? RANK_TABLE_M : RANK_TABLE_F;
  const [cats, weightClass] = rankCategory(table, bodyweight);
  const th = table[weightClass];
  const last = RANK_ORDER[RANK_ORDER.length - 1];
  let achieved = "нет разряда";
  let nextRank = last;
  let gap = th[last] ? th[last] - total : 0.0;
  for (let i = 0; i < RANK_ORDER.length; i++) {
    const t = th[RANK_ORDER[i]];
    if (t !== null && total >= t) {
      achieved = RANK_ORDER[i];
      nextRank = null;
      gap = 0.0;
      for (let j = i - 1; j >= 0; j--) {
        if (th[RANK_ORDER[j]] !== null) {
          nextRank = RANK_ORDER[j];
          gap = th[RANK_ORDER[j]] - total;
          break;
        }
      }
      break;
    }
  }
  const label = weightClass !== 999 ? `${weightClass}` : `${cats[cats.length - 2]}+`;
  return { weight_class: label, rank: achieved, next_rank: nextRank, gap_to_next: gap };
}

// ---------------------------------------------------------------------------
// Помощники из wizard.py / cards.py
// ---------------------------------------------------------------------------

export const STRENGTH_SCALE = [100, 600, ["новичок", "любитель", "продвинутый", "элита", "топ"]];
export const FFMI_SCALE = [15, 28, ["низкий", "средний", "хороший", "предел", "выше"]];

export function rankLadder(sex, bodyweight) {
  const table = sex === "m" ? RANK_TABLE_M : RANK_TABLE_F;
  const [, cat] = rankCategory(table, bodyweight);
  return RANK_ORDER.map((name) => [name, table[cat][name]]);
}

export function scaleLabel(value, [vmin, vmax, labels]) {
  const t = Math.max(0, Math.min(1, (value - vmin) / (vmax - vmin)));
  return labels[Math.min(labels.length - 1, Math.trunc(t * labels.length))];
}

/** Любая цель для любого возраста; до 18 лет — предупреждение (как в боте). */
export function kbjuWithGuard(sex, age, height, weight, activity, goal) {
  let note = null;
  if (age < 18) {
    note = "До 18 лет — грубый ориентир: формула выведена на взрослых.";
    if (goal === "cut") note += " Дефицит лучше согласовать с врачом.";
  }
  return [calcKbju(sex, age, height, weight, activity, goal), note];
}

export function repsWord(n) {
  if (n % 10 === 1 && n % 100 !== 11) return "повтор";
  if (n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14)) return "повтора";
  return "повторов";
}
