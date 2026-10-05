#!/usr/bin/env node
// telemetry-helpers.test.mjs — offline fixture-тесты T-124 Telemetry P0 (ECO-002).
// Запуск: node opencode-global/.config/opencode/lib/telemetry-helpers.test.mjs
// Только встроенные модули node (assert/fs/path/url), без сети и внешних
// зависимостей. Пишет ТОЛЬКО во временные fixture-пути /tmp/opencode/
// telemetry-test-* — реальный control-plane НЕ трогается.
//
// Все секретоподобные строки ниже — ФИКТИВНЫЕ, только для проверки redaction.
//
// Main-guard: тесты выполняются только при прямом запуске (`node <file>`).
// При auto-discovery-импорте (если lib/ грузится как каталог плагинов) модуль
// безвреден: callable default-экспорт и ноль побочных эффектов — та же
// конвенция, что у остальных модулей lib/.

import assert from "node:assert/strict"
import { existsSync, mkdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { fileURLToPath } from "node:url"
import {
  appendJsonlRecord,
  buildAuditRecord,
  buildReport,
  buildTokenRecord,
  estimateTokens,
  readJsonlLines,
  redactFields,
  redactString,
} from "./telemetry-helpers.js"

const isMain = (() => {
  if (!process.argv[1]) return false
  try {
    return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url))
  } catch {
    return false
  }
})()

// --- fixture-пути (только /tmp/opencode/...) ---------------------------------

let tmpRoot
function tmp() {
  if (tmpRoot === undefined) {
    tmpRoot = join("/tmp/opencode", `telemetry-test-${process.pid}-${Date.now()}`)
    rmSync(tmpRoot, { recursive: true, force: true })
    mkdirSync(tmpRoot, { recursive: true })
  }
  return tmpRoot
}

const tests = []
function test(name, fn) {
  tests.push({ name, fn })
}

// --- 1. Redaction: каждый из 5 паттернов (T-124 §4a) --------------------------

test("redact: sk- pattern", () => {
  assert.equal(redactString("key sk-FAKEkey0000011111 used"), "key [REDACTED] used")
})

test("redact: Bearer pattern", () => {
  assert.equal(
    redactString("Authorization: Bearer FAKEbearer12345678 end"),
    "Authorization: [REDACTED] end",
  )
})

test("redact: api_key pattern (keyword + value)", () => {
  assert.equal(redactString("api_key=FAKEapi123456 ok"), "[REDACTED] ok")
})

test("redact: password pattern (keyword + value)", () => {
  assert.equal(redactString("password=FAKEpass9876 x"), "[REDACTED] x")
})

test("redact: token= pattern (keyword + value)", () => {
  assert.equal(redactString("token=FAKEtoken5555 y"), "[REDACTED] y")
})

test("redact: quoted json form (\"password\": \"...\")", () => {
  assert.equal(redactString('cfg {"password": "FAKEp12"} end'), 'cfg {"[REDACTED]"} end')
})

test("redact: no false positives on token metadata words", () => {
  const src = "input_tokens=1500 output_tokens=200 token_budget ran"
  assert.equal(redactString(src), src)
})

test("redactFields: secret-named keys → key+value redacted (nested)", () => {
  const out = redactFields({ password: "FAKEpw1", nested: [{ api_key: "FAKEak2" }], label: "clean" })
  assert.deepEqual(out, {
    "[REDACTED]": "[REDACTED]",
    nested: [{ "[REDACTED]": "[REDACTED]" }],
    label: "clean",
  })
})

test("redactFields: strings inside nested arrays/objects", () => {
  const out = redactFields({ a: ["sk-FAKEkey0000011111", { b: "password=FAKEpw22" }] })
  assert.deepEqual(out, { a: ["[REDACTED]", { b: "[REDACTED]" }] })
})

test("redactFields: input_tokens/output_tokens keys survive key-redaction", () => {
  const src = { input_tokens: 100, output_tokens: 50, estimated: true }
  assert.deepEqual(redactFields(src), src)
})

test("redactFields: content-like keys (prompt/response) → value withheld", () => {
  const out = redactFields({ prompt: "hello world", nested: { response: "x", keep: 7 } })
  assert.deepEqual(out, { prompt: "[REDACTED]", nested: { response: "[REDACTED]", keep: 7 } })
})

test("redactFields: content gate covers new keys (system/reply/answer/stdout/stderr/arguments/result/history/transcript/summary/note/data)", () => {
  const gated = [
    "system",
    "reply",
    "answer",
    "stdout",
    "stderr",
    "arguments",
    "result",
    "history",
    "transcript",
    "summary",
    "note",
    "data",
  ]
  const input = { label: "keep" }
  const expected = { label: "keep" }
  for (const key of gated) {
    input[key] = `plain ${key} payload`
    expected[key] = "[REDACTED]"
  }
  assert.deepEqual(redactFields(input), expected)
})

test("redactFields: details strings >160 chars truncated with marker", () => {
  const long = "x".repeat(200)
  const out = redactFields({ long_field: long, nested: { deep: long } })
  const truncated = "x".repeat(160) + "…[TRUNCATED]"
  assert.equal(out.long_field, truncated)
  assert.equal(out.nested.deep, truncated)
  // граница «длиннее 160»: 161 символ тоже обрезается
  assert.equal(redactFields({ k: "y".repeat(161) }).k, "y".repeat(160) + "…[TRUNCATED]")
  // redaction применяется ПОСЛЕ обрезки: секрет до границы всё равно вырезается
  const withSecret = "z".repeat(150) + "password=FAKElongsecret1" + "z".repeat(60)
  const redacted = redactFields({ k: withSecret })
  assert.ok(!redacted.k.includes("FAKElongsecret1"))
})

test("redactFields: strings ≤160 chars pass without truncation", () => {
  assert.equal(redactFields({ k: "x".repeat(160) }).k, "x".repeat(160))
  assert.equal(redactFields({ k: "x".repeat(159) }).k, "x".repeat(159))
  assert.equal(redactFields({ k: "short" }).k, "short")
})

test("truncation: не применяется к полям самой записи (action/session_id), только к details", () => {
  const long = "a".repeat(200)
  const rec = buildAuditRecord({ action: long, session_id: `ses_${"s".repeat(200)}` })
  assert.equal(rec.action.length, 200)
  assert.equal(rec.session_id.length, 204)
  const withDetails = buildAuditRecord({ action: "x", details: { k: long } })
  assert.equal(withDetails.details.k, "a".repeat(160) + "…[TRUNCATED]")
})

test("redactFields: deeper than 8 levels → value fully [REDACTED]", () => {
  const wrap = (levels, value) => {
    let out = value
    for (let i = 0; i < levels; i += 1) out = { k: out }
    return out
  }
  // глубина 8 — ещё обрабатывается: чистая строка проходит как есть
  const atLimit = redactFields(wrap(8, "clean leaf value"))
  assert.equal(atLimit.k.k.k.k.k.k.k.k, "clean leaf value")
  // глубина 9 — значение (строка/объект) заменяется целиком
  assert.equal(redactFields(wrap(9, "clean leaf value")).k.k.k.k.k.k.k.k.k, "[REDACTED]")
  assert.equal(redactFields(wrap(9, { a: 1 })).k.k.k.k.k.k.k.k.k, "[REDACTED]")
})

// --- 2. audit-log record --------------------------------------------------------

test("audit record: whitelists known fields, drops prompt-like extras", () => {
  const rec = buildAuditRecord({
    action: "tool:grep",
    session_id: "ses_1",
    task_id: "T-124",
    duration_ms: 12,
    prompt: "PROMPT_MARKER_secret conv", // вне схемы → отбрасывается
    content: "model said something", // вне схемы → отбрасывается
    details: { files: 2 },
  })
  const serialized = JSON.stringify(rec)
  assert.ok(!serialized.includes("PROMPT_MARKER"))
  assert.ok(!serialized.includes("model said"))
  assert.equal(rec.action, "tool:grep")
  assert.equal(rec.session_id, "ses_1")
  assert.equal(rec.task_id, "T-124")
  assert.equal(rec.duration_ms, 12)
  assert.deepEqual(rec.details, { files: 2 })
})

test("audit record: ts is ISO-8601 (and respects explicit now)", () => {
  const rec = buildAuditRecord({ action: "x" }, "2026-10-03T10:00:00.000Z")
  assert.equal(rec.ts, "2026-10-03T10:00:00.000Z")
  assert.match(rec.ts, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/)
})

test("audit record: deterministic key order", () => {
  const rec = buildAuditRecord({
    action: "a",
    session_id: "s",
    task_id: "t",
    duration_ms: 1,
    details: {},
  })
  assert.deepEqual(Object.keys(rec), [
    "ts",
    "session_id",
    "task_id",
    "action",
    "duration_ms",
    "details",
  ])
})

test("audit record: string fields pass redaction", () => {
  const rec = buildAuditRecord({
    action: "used sk-FAKEkey0000011111",
    details: { note: "token=FAKEtoken77" },
  })
  assert.equal(rec.action, "used [REDACTED]")
  assert.deepEqual(rec.details, { note: "[REDACTED]" })
})

test("audit record: omits absent optional fields", () => {
  const rec = buildAuditRecord({ action: "only" })
  assert.deepEqual(Object.keys(rec), ["ts", "action"])
})

// --- 3. append-only storage (T-124 §4a) ----------------------------------------

test("append: creates missing dir and file, writes valid JSONL", () => {
  const path = join(tmp(), "create-missing", "nested", "audit-log.jsonl")
  appendJsonlRecord(path, { ts: "2026-10-03T10:00:00.000Z", action: "x" })
  assert.ok(existsSync(path))
  const lines = readJsonlLines(path)
  assert.equal(lines.length, 1)
  assert.equal(JSON.parse(lines[0]).action, "x")
})

test("append: existing lines unchanged byte-for-byte", () => {
  const dir = join(tmp(), "append-intact")
  mkdirSync(dir, { recursive: true })
  const path = join(dir, "audit-log.jsonl")
  const first = JSON.stringify({ ts: "2026-10-03T10:00:00.000Z", action: "first" })
  writeFileSync(path, first + "\n", "utf8")
  const before = readFileSync(path, "utf8")
  appendJsonlRecord(path, { ts: "2026-10-03T10:00:01.000Z", action: "second" })
  const after = readFileSync(path, "utf8")
  assert.ok(after.startsWith(before))
  const lines = readJsonlLines(path)
  assert.equal(lines.length, 2)
  assert.equal(lines[0], first)
  assert.equal(JSON.parse(lines[1]).action, "second")
})

test("append: broken tail (no trailing newline) — history kept, new line intact", () => {
  const dir = join(tmp(), "broken-tail")
  mkdirSync(dir, { recursive: true })
  const path = join(dir, "audit-log.jsonl")
  const good = JSON.stringify({ ts: "2026-10-03T09:00:00.000Z", action: "good" })
  const broken = '{"ts":"2026-10-03T09:30:00.000Z","action":"bro' // недописанная строка
  writeFileSync(path, good + "\n" + broken, "utf8") // файл БЕЗ завершающего \n
  const before = readFileSync(path, "utf8")
  appendJsonlRecord(path, { ts: "2026-10-03T10:00:00.000Z", action: "fresh" })
  const after = readFileSync(path, "utf8")
  assert.ok(after.startsWith(before)) // история байт-в-байт не тронута
  const lines = readJsonlLines(path)
  assert.equal(lines.length, 3) // good | broken | fresh
  assert.equal(JSON.parse(lines[0]).action, "good")
  assert.equal(lines[1], broken) // битая строка не «починена» перезаписью
  assert.equal(JSON.parse(lines[2]).action, "fresh")
})

test("append: newline-terminated file gets no blank line", () => {
  const path = join(tmp(), "newline-ok", "audit-log.jsonl")
  appendJsonlRecord(path, { action: "one" })
  appendJsonlRecord(path, { action: "two" })
  const text = readFileSync(path, "utf8")
  assert.ok(!text.includes("\n\n"))
  assert.equal(readJsonlLines(path).length, 2)
})

test("append: final-pass redaction over serialized line, JSON stays valid", () => {
  const path = join(tmp(), "final-pass", "audit-log.jsonl")
  appendJsonlRecord(path, { note: "config had api_key=FAKEserialized123 inside" })
  const text = readFileSync(path, "utf8")
  assert.ok(!text.includes("FAKEserialized123"))
  assert.ok(text.includes("[REDACTED]"))
  JSON.parse(readJsonlLines(path)[0]) // не бросает — строка валидный JSON
})

// --- 4. token-budget records (T-124 §4a: корректный подсчёт) --------------------

test("token record: explicit numbers, estimated=false, fixed key order", () => {
  const rec = buildTokenRecord({
    session_id: "ses_1",
    model: "m1",
    input_tokens: 100,
    output_tokens: 40,
  })
  assert.equal(rec.input_tokens, 100)
  assert.equal(rec.output_tokens, 40)
  assert.equal(rec.estimated, false)
  assert.equal(rec.session_id, "ses_1")
  assert.deepEqual(Object.keys(rec), [
    "ts",
    "session_id",
    "model",
    "input_tokens",
    "output_tokens",
    "estimated",
  ])
})

test("token record: text estimate — deterministic, estimated=true", () => {
  const rec = buildTokenRecord({ session_id: "ses_1", text: "a".repeat(101) })
  assert.equal(rec.input_tokens, 26) // ceil(101/4)
  assert.equal(rec.output_tokens, 0)
  assert.equal(rec.estimated, true)
  assert.equal(rec.model, undefined)
  assert.deepEqual(Object.keys(rec), [
    "ts",
    "session_id",
    "input_tokens",
    "output_tokens",
    "estimated",
  ])
})

test("token record: explicit numbers win over text", () => {
  const rec = buildTokenRecord({ session_id: "s", input_tokens: 10, text: "a".repeat(400) })
  assert.equal(rec.input_tokens, 10)
  assert.equal(rec.estimated, false)
})

test("token record: throws without session_id", () => {
  assert.throws(() => buildTokenRecord({ input_tokens: 1 }), /session_id/)
})

test("token record: throws with neither numbers nor text", () => {
  assert.throws(
    () => buildTokenRecord({ session_id: "s" }),
    /input_tokens\/output_tokens \(numbers\) or text/,
  )
})

test("token record: rejects negative counts", () => {
  assert.throws(() => buildTokenRecord({ session_id: "s", input_tokens: -5 }), /non-negative/)
})

test("estimateTokens: deterministic ceil(len/4)", () => {
  assert.equal(estimateTokens(""), 0)
  assert.equal(estimateTokens("abcd"), 1)
  assert.equal(estimateTokens("abcde"), 2)
  assert.equal(estimateTokens("a".repeat(101)), 26)
  assert.equal(estimateTokens(null), 0)
})

test("token record: estimated text itself is never stored", () => {
  const rec = buildTokenRecord({
    session_id: "ses_x",
    text: "LEAKTEST_PROMPT sk-FAKEkey0000011111",
  })
  const serialized = JSON.stringify(rec)
  assert.ok(!serialized.includes("LEAKTEST_PROMPT"))
  assert.ok(!serialized.includes("sk-FAKEkey"))
  assert.equal(rec.input_tokens, estimateTokens("LEAKTEST_PROMPT sk-FAKEkey0000011111"))
})

test("readJsonlLines: missing file → []", () => {
  assert.deepEqual(readJsonlLines(join(tmp(), "missing.jsonl")), [])
})

// --- 5. детерминированный отчёт (T-124 §4e) ---------------------------------------

const NOW = "2026-10-03T12:00:00.000Z"

function fixtureLines() {
  return [
    JSON.stringify({
      ts: "2026-10-01T10:00:00.000Z",
      session_id: "ses_a",
      model: "glm-5.3",
      input_tokens: 1000,
      output_tokens: 500,
      estimated: false,
    }),
    JSON.stringify({
      ts: "2026-10-02T10:00:00.000Z",
      session_id: "ses_a",
      model: "glm-5.3",
      input_tokens: 2000,
      output_tokens: 700,
      estimated: false,
    }),
    JSON.stringify({
      ts: "2026-10-03T09:00:00.000Z",
      session_id: "ses_b",
      model: "gpt-5.6",
      input_tokens: 400,
      output_tokens: 100,
      estimated: true,
    }),
    JSON.stringify({
      ts: "2026-09-20T12:00:00.000Z", // вне недельного окна
      session_id: "ses_a",
      model: "glm-5.3",
      input_tokens: 9999,
      output_tokens: 9999,
      estimated: false,
    }),
    '{"ts":"2026-10-03T10:00:00.000Z","action"', // битая строка
  ]
}

test("report: week — sums, window filter, malformed skipped, breakdown", () => {
  const report = buildReport(fixtureLines(), "week", { now: NOW })
  assert.ok(report.includes("period: week"))
  assert.ok(
    report.includes("window: 2026-09-26T12:00:00.000Z .. 2026-10-03T12:00:00.000Z"),
  )
  assert.ok(report.includes("records: 3 in period (malformed skipped: 1, estimated: 1)"))
  assert.ok(report.includes("totals: input=3400 output=1300 total=4700"))
  assert.ok(!report.includes("9999")) // запись вне окна не попадает в отчёт
  assert.ok(report.includes("ses_a"))
  assert.ok(report.includes("ses_b"))
  assert.ok(report.includes("glm-5.3"))
  assert.ok(report.includes("gpt-5.6"))
})

test("report: day — only last 24h", () => {
  const report = buildReport(fixtureLines(), "day", { now: NOW })
  assert.ok(report.includes("records: 1 in period"))
  assert.ok(report.includes("totals: input=400 output=100 total=500"))
})

test("report: all — every parseable record", () => {
  const report = buildReport(fixtureLines(), "all", {})
  assert.ok(report.includes("window: all time"))
  assert.ok(report.includes("records: 4 in period (malformed skipped: 1, estimated: 1)"))
  assert.ok(report.includes("totals: input=13399 output=11299 total=24698"))
})

test("report: reference from log records (no Date.now), double run identical", () => {
  const a = buildReport(fixtureLines(), "week")
  const b = buildReport(fixtureLines(), "week")
  assert.equal(a, b)
  assert.ok(a.includes("window: 2026-09-26T09:00:00.000Z .. 2026-10-03T09:00:00.000Z"))
  assert.ok(a.includes("totals: input=3400 output=1300 total=4700"))
})

test("report: fixture log via file — byte-for-byte identical double run", () => {
  const dir = join(tmp(), "det")
  mkdirSync(dir, { recursive: true })
  const path = join(dir, "token-budget.jsonl")
  writeFileSync(path, fixtureLines().join("\n") + "\n", "utf8")
  const a = buildReport(readJsonlLines(path), "week", { threshold: 100 })
  const b = buildReport(readJsonlLines(path), "week", { threshold: 100 })
  assert.equal(a, b)
  assert.ok(Buffer.from(a).equals(Buffer.from(b)))
  assert.ok(a.startsWith("WARNING")) // 4700 > 100
})

test("report: threshold exceeded → report starts with warning", () => {
  const report = buildReport(fixtureLines(), "week", { now: NOW, threshold: 4699 })
  assert.ok(report.startsWith("WARNING"))
  assert.ok(report.includes("4700"))
  assert.ok(report.includes("4699"))
})

test("report: threshold not exceeded → no warning", () => {
  const report = buildReport(fixtureLines(), "week", { now: NOW, threshold: 100000 })
  assert.ok(!report.includes("WARNING"))
  assert.ok(!report.includes("threshold"))
})

test("report: session filter", () => {
  const report = buildReport(fixtureLines(), "all", { sessionId: "ses_b" })
  assert.ok(report.includes("records: 1 in period"))
  assert.ok(report.includes("totals: input=400 output=100 total=500"))
  assert.ok(!report.includes("ses_a"))
})

test("report: empty log", () => {
  const report = buildReport([], "week", {})
  assert.ok(report.includes("records: 0 in period (malformed skipped: 0, estimated: 0)"))
  assert.ok(report.includes("no records in period"))
  // без записей и без явного now окно не рисуется фальшью 1969/1970
  assert.ok(report.includes("window: n/a (no records)"))
  assert.ok(!report.includes("1969"))
  // явное now даже = epoch → честное окно от него
  const explicit = buildReport([], "week", { now: 0 })
  assert.ok(explicit.includes("window: 1969-12-25T00:00:00.000Z .. 1970-01-01T00:00:00.000Z"))
})

test("report: invalid period throws", () => {
  assert.throws(() => buildReport([], "month", {}), /period must be/)
})

test("report: missing log file → empty report", () => {
  const path = join(tmp(), "no-such-dir", "token-budget.jsonl")
  const report = buildReport(readJsonlLines(path), "all", {})
  assert.ok(report.includes("records: 0 in period"))
})

// --- 6. end-to-end + leak-proof (T-124 §4b) --------------------------------------

test("e2e: token records via append → report reads them back", () => {
  const path = join(tmp(), "e2e", "token-budget.jsonl")
  appendJsonlRecord(
    path,
    buildTokenRecord({ session_id: "ses_e2e", model: "glm-5.3", input_tokens: 10, output_tokens: 4 }),
  )
  appendJsonlRecord(
    path,
    buildTokenRecord({ session_id: "ses_e2e", model: "glm-5.3", text: "x".repeat(40) }), // 10 токенов
  )
  const report = buildReport(readJsonlLines(path), "all", {})
  assert.ok(report.includes("records: 2 in period"))
  assert.ok(report.includes("totals: input=20 output=4 total=24"))
  assert.ok(report.includes("estimated: 1"))
})

test("leak-proof §4(b): prompt text and secret never land in audit log", () => {
  const path = join(tmp(), "leak-proof", "audit-log.jsonl")
  // Фиктивные строки для проверки redaction — не реальные секреты:
  const secret = "sk-FAKEleak0001112233445"
  const promptMarker = "LEAKTEST_PROMPT_MARKER deploy the cluster now"
  appendJsonlRecord(
    path,
    buildAuditRecord({
      action: "tool:run",
      session_id: "ses_leak",
      prompt: promptMarker, // вне схемы → отбрасывается
      messages: [{ user: promptMarker }], // вне схемы → отбрасывается
      details: {
        note: `ran with ${secret}`, // строковое поле → redaction
        password: "FAKEleakpw9", // секретный ключ → вырезан
        prompt: promptMarker, // content-ключ → вырезан
      },
    }),
  )
  const text = readFileSync(path, "utf8")
  // grep-эквивалент: ни секрета, ни промпта в логе нет
  assert.ok(!text.includes(secret))
  assert.ok(!text.includes("LEAKTEST_PROMPT_MARKER"))
  assert.ok(!text.includes("FAKEleakpw9"))
  assert.ok(!text.includes("deploy the cluster"))
  // метаданные на месте, лог валиден, redaction оставил маркеры
  assert.ok(text.includes('"session_id":"ses_leak"'))
  assert.ok(text.includes('"prompt":"[REDACTED]"'))
  JSON.parse(readJsonlLines(path)[0])
})

// --- runner ----------------------------------------------------------------------

function run() {
  const failed = []
  for (const { name, fn } of tests) {
    try {
      fn()
    } catch (err) {
      failed.push({ name, err })
    }
  }
  for (const { name, err } of failed) {
    const head = err && err.stack ? err.stack.split("\n").slice(0, 3).join("\n    ") : String(err)
    console.error(`FAIL: ${name}\n    ${head}`)
  }
  const passed = tests.length - failed.length
  console.log(`telemetry-helpers tests: ${passed}/${tests.length} passed`)
  return failed.length === 0 ? 0 : 1
}

// Auto-discovery guard: callable default, без побочных эффектов.
export default async () => ({})

if (isMain) {
  process.exitCode = run()
  if (tmpRoot !== undefined) rmSync(tmpRoot, { recursive: true, force: true })
}
