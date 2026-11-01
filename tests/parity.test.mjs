// Сверка webapp/calc.js с calculators.py: node tests/parity.test.mjs
// Сначала: python tests/make_fixtures.py (пишет tests/fixtures.json)
import { readFileSync } from "node:fs";
import * as C from "../webapp/calc.js";

const data = JSON.parse(readFileSync(new URL("./fixtures.json", import.meta.url), "utf8"));
const FN = {
  calc_1rm: C.calc1rm, calc_dots: C.calcDots, calc_wilks: C.calcWilks, calc_ffmi: C.calcFfmi,
  calc_kbju: C.calcKbju, calc_rpe: C.calcRpe, generate_warmup: C.generateWarmup, calc_rank: C.calcRank,
};

const norm = (x) => (x === Infinity ? "inf" : x);

function same(a, b, path) {
  a = norm(a);
  if (typeof b === "number" && typeof a === "number") {
    const tol = 1e-9 * Math.max(1, Math.abs(b));
    if (Math.abs(a - b) > tol) return `${path}: js=${a} py=${b}`;
    return null;
  }
  if (Array.isArray(b)) {
    if (!Array.isArray(a) || a.length !== b.length) return `${path}: длина js=${a?.length} py=${b.length}`;
    for (let i = 0; i < b.length; i++) { const e = same(a[i], b[i], `${path}[${i}]`); if (e) return e; }
    return null;
  }
  if (b && typeof b === "object") {
    for (const k of Object.keys(b)) { const e = same(a?.[k], b[k], `${path}.${k}`); if (e) return e; }
    return null;
  }
  return a === b ? null : `${path}: js=${JSON.stringify(a)} py=${JSON.stringify(b)}`;
}

let fails = 0, n = 0;
const fail = (msg) => { fails++; if (fails <= 20) console.error("✗", msg); };

for (const c of data.cases) {
  n++;
  let js;
  try { js = { ok: FN[c.fn](...c.args) }; } catch (e) { js = { error: e.message }; }
  const label = `${c.fn}(${c.args.join(", ")})`;
  if ("error" in c.out) {
    if (!("error" in js)) fail(`${label}: Python ошибка «${c.out.error}», JS посчитал`);
    else if (js.error !== c.out.error) fail(`${label}: текст ошибки js=«${js.error}» py=«${c.out.error}»`);
    continue;
  }
  if ("error" in js) { fail(`${label}: JS ошибка «${js.error}»`); continue; }
  const e = same(js.ok, c.out.ok, label);
  if (e) fail(e);
}
for (const f of data.fmt) {
  n++;
  const js = C.num(f.v, f.d);
  if (js !== f.out) fail(`num(${f.v}, ${f.d}): js=${js} py=${f.out}`);
}
for (const r of data.round) {
  n++;
  if (C.pyRound(r.v) !== r.out) fail(`round(${r.v}): js=${C.pyRound(r.v)} py=${r.out}`);
}

console.log(fails ? `ПРОВАЛ: ${fails} из ${n}` : `OK: ${n} проверок, JS = Python`);
process.exit(fails ? 1 : 0);
