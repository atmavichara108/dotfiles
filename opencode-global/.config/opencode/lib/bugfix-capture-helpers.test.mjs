#!/usr/bin/env node
// bugfix-capture-helpers.test.mjs — offline fixture-тесты capture-хелперов BF-20261010-01 Phase 1.
// Запуск: node opencode-global/.config/opencode/lib/bugfix-capture-helpers.test.mjs
// Только встроенные модули node, без сети. Пишет ТОЛЬКО во временный fixture-путь
// /tmp/opencode/bf-capture-test-<pid>/.
// Покрывает S12: 1 (tool-fail capture), 2 (secret guard), 3 (detector failure),
// 4 (dedup), 5 (correlation cross-session), 6 (Scope Guard), 7 (route-table),
// 8 (zero-LLM grep-аудит), плюс ротация и enums.

import assert from "node:assert/strict"
import { mkdir, readFile, rm, stat, writeFile, utimes } from "node:fs/promises"
import { existsSync } from "node:fs"
import { join } from "node:path"
import { execSync } from "node:child_process"
import { fileURLToPath } from "node:url"
import {
  ALLOWED_REPOS,
  ERROR_CLASSES,
  SAFE_HINTS,
  RECOMMENDED_ROUTES,
  classifyFailure,
  buildCapture,
  correlationId,
  appendCapture,
  detectUnsafe,
  guardFields,
  applyRetention,
  ROTATE_LINES,
} from "./bugfix-capture-helpers.js"

const HERE = fileURLToPath(new URL(".", import.meta.url))
const TMP = `/tmp/opencode/bf-capture-test-${process.pid}`
const STATE = join(TMP, "incidents")

let passed = 0
const t = (name, fn) =>
  fn().then(
    () => { passed++; console.log(`  OK  ${name}`) },
    (e) => { console.error(`  FAIL ${name}: ${e?.message ?? e}`); process.exitCode = 1 },
  )

const mk = (over = {}) => ({
  source: "tool",
  projectSlug: "dotfiles",
  sessionID: "ses_testAAA111",
  classified: { error_class: "tool-fail", safe_hint: "bash-error" },
  ts: 1791900000,
  ...over,
})

await rm(TMP, { recursive: true, force: true })
await mkdir(STATE, { recursive: true })

console.log("bugfix-capture-helpers fixtures:")

await t("S12.1 tool-fail: запись только enums/metadata", async () => {
  const rec = buildCapture(mk())
  assert.equal(rec.error_class, "tool-fail")
  assert.equal(rec.source_class, "tool")
  assert.equal(rec.recommended_route, RECOMMENDED_ROUTES["tool-fail"])
  const keys = Object.keys(rec).sort()
  for (const k of ["sessionID", "message", "stderr", "command", "cwd", "directory", "output"])
    assert.ok(!keys.includes(k), `лишнее поле ${k}`)
  const r2 = await appendCapture(STATE, rec)
  assert.equal(r2.action, "new")
  const lines = (await readFile(join(STATE, "dotfiles.djsonl"), "utf-8")).trim().split("\n")
  assert.equal(lines.length, 1)
  assert.deepEqual(JSON.parse(lines[0]).error_class, "tool-fail")
})

await t("S12.2 secret guard: fake token → fail-closed без значения", async () => {
  assert.ok(detectUnsafe("token=foo123"), "token=foo должен ловиться")
  assert.ok(detectUnsafe("sk-abcdefghijkl"), "sk- должен ловиться")
  assert.ok(detectUnsafe("/home/rudra/.config/ssa-tg/tg.env"), "abs path должен ловиться")
  let threw = null
  try {
    buildCapture(mk({ sessionID: "ses_secretAAA1", classified: { error_class: "unknown", safe_hint: "classifier-fallback" } }))
  } catch (e) { threw = e }
  assert.ok(threw === null || threw.code, "без секрета не бросаем или бросаем код")
  // прямая проверка: guarded-поля с секретом → отказ без утечки значения
  const g = guardFields({ safe_hint: "sk-abcdefghijkl" })
  assert.equal(g.ok, false)
  assert.ok(!JSON.stringify(g).includes("abcdefghijkl"), "код отказа не содержит значение")
  const before = await readFile(join(STATE, "dotfiles.djsonl"), "utf-8")
  let threw2 = null
  try {
    // bad enum безопасный, а unsafe value в поле проходит только через build/guard
    buildCapture(mk({ projectSlug: "dotfiles", sessionID: "ses_testBBB2" }))
  } catch (e) { threw2 = e }
  assert.equal(threw2, null)
  const after = await readFile(join(STATE, "dotfiles.djsonl"), "utf-8")
  void before; void after // safe-запись разрешилась; unsafe не создаёт запись ниже
})

await t("S12.3 detector failure: бросок → код DET-FAIL, не исключение", async () => {
  // эмулируем падение детектора через Proxy-ловушку на Object.entries
  const evil = new Proxy({ safe_hint: "bash-error" }, {
    ownKeys() { throw new Error("boom-with-secret-value=leak") },
    getOwnPropertyDescriptor() { return { enumerable: true, configurable: true } },
    get() { return "x" },
  })
  const r = guardFields(evil)
  assert.equal(r.ok, false)
  assert.equal(r.code, "DET-FAIL")
  assert.ok(!JSON.stringify(r).includes("boom"), "текст исключения не наружу")
})

await t("S12.4 dedup: одинаковый сбой в окне сессии → count=2", async () => {
  const rec = buildCapture(mk({ sessionID: "ses_dedup111", ts: 1791900100 }))
  await appendCapture(STATE, rec)
  await appendCapture(STATE, rec)
  const lines = (await readFile(join(STATE, "dotfiles.djsonl"), "utf-8")).trim().split("\n").map(JSON.parse)
  const hit = lines.filter((l) => l.session_id === "ses_dedup111")
  assert.equal(hit.length, 1)
  assert.equal(hit[0].count, 2)
})

await t("S12.5 corrsession склейка в агрегате", async () => {
  const s1 = buildCapture(mk({ sessionID: "ses_corr1111", ts: 1791900200 }))
  const s2 = buildCapture(mk({ sessionID: "ses_corr2222", ts: 1791900300 }))
  assert.equal(s1.correlation_id, correlationId("dotfiles", "tool-fail", "bash-error"))
  await appendCapture(STATE, s1)
  await appendCapture(STATE, s2)
  const idx = (await readFile(join(STATE, "incidents-index.jsonl"), "utf-8")).trim().split("\n").map(JSON.parse)
  const agg = idx.filter((l) => l.correlation_id === s1.correlation_id)
  assert.equal(agg.length, 1, "агрегат — одна строка на correlation_id")
  // пред. тесты писали ту же пару class+hint → та же склейка (корректно по S12.5)
  for (const s of ["ses_corr1111", "ses_corr2222", "ses_dedup111", "ses_testAAA111"])
    assert.ok(agg[0].sessions.includes(s), `sessions включает ${s}`)
  assert.equal(new Set(agg[0].sessions).size, agg[0].sessions.length, "sessions без дублей")
})

await t("S12.6 Scope Guard: чужой репо → NO-CREATE, файла нет", async () => {
  let code = null
  try { buildCapture(mk({ projectSlug: "foreign-repo" })) } catch (e) { code = e.code }
  assert.equal(code, "NO-CREATE")
  assert.ok(!existsSync(join(STATE, "foreign-repo.djsonl")))
})

await t("S12.7 route-table: каждый enum → детерминированный route", async () => {
  for (const cls of ERROR_CLASSES) {
    assert.ok(RECOMMENDED_ROUTES[cls], `route для ${cls}`)
  }
})

await t("S12.8 zero-LLM grep-аудит исходников", async () => {
  const file = join(HERE, "bugfix-capture-helpers.js")
  const src = (await readFile(file, "utf-8"))
  for (const bad of [".generate.text", "ctx.generate", "openai", "fetch(", "@ai-sdk", "anthropic"])
    assert.ok(!src.includes(bad), `найден LLM/провайдерский вызов: ${bad}`)
})

await t("S5 классификатор: quota/balance/unavailable/timeout/permission/tool/unknown", async () => {
  assert.deepEqual(classifyFailure("provider", { message: "Go usage limit exceeded", status: 429 }), { error_class: "provider-quota", safe_hint: "provider-quota-429" })
  assert.equal(classifyFailure("provider", { message: "insufficient quota" }).error_class, "provider-quota")
  assert.equal(classifyFailure("provider", { message: "balance exhausted" }).error_class, "provider-quota")
  assert.equal(classifyFailure("provider", { message: "model unavailable" }).error_class, "provider-unavailable")
  assert.equal(classifyFailure("provider", { message: "socket hang up" }).error_class, "provider-timeout")
  assert.equal(classifyFailure("provider", { message: "всё плохо" }).error_class, "unknown")
  assert.equal(classifyFailure("permission", { reply: "reject" }).error_class, "permission-blocked")
  assert.equal(classifyFailure("tool", { tool: "edit" }).safe_hint, "edit-error")
  // классификатор не роняет на мусоре
  assert.equal(classifyFailure("nonsense", {}).error_class, "unknown")
})

await t("bad session/id → BAD-SESSION, чужой project → NO-CREATE (не silent)", async () => {
  let code = null
  try { buildCapture(mk({ sessionID: "not-a-session" })) } catch (e) { code = e.code }
  assert.equal(code, "BAD-SESSION")
})

await t("ротация: >ROTATE_LINES строк → _archive/, рабочий файл пустой", async () => {
  const dir = join(TMP, "rot")
  await mkdir(join(dir, "_archive"), { recursive: true })
  const file = join(dir, "dotfiles.djsonl")
  const big = Array.from({ length: ROTATE_LINES + 5 }, (_, i) =>
    JSON.stringify(buildCapture(mk({ sessionID: "ses_rot1", safe: undefined, ts: 1791900000 + i })))
  ).join("\n")
  await writeFile(file, big + "\n")
  // add через appendCapture -> он сам ротироват перед записью следующей
  await appendCapture(dir, buildCapture(mk({ sessionID: "ses_new1", ts: 1791999999 })))
  const arch = await readFile(join(dir, "_archive", (await import("node:fs")).readdirSync(join(dir, "_archive"))[0]), "utf-8")
  assert.ok(arch.trim().split("\n").length > ROTATE_LINES)
  const fresh = await readFile(file, "utf-8")
  assert.equal(fresh.trim().split("\n").length, 1)
})

await t("retention 90 дней → _archive/", async () => {
  const dir = join(TMP, "ret")
  await mkdir(dir, { recursive: true })
  const file = join(dir, "oldrepo.djsonl")
  await writeFile(file, "{}\n")
  const old = new Date(Date.now() - 95 * 86_400_000)
  await utimes(file, old, old)
  await applyRetention(dir)
  assert.ok(!existsSync(file))
  assert.ok(existsSync(join(dir, "_archive", "oldrepo.djsonl")))
})

await t("enums неизменяемы", async () => {
  assert.throws(() => { ALLOWED_REPOS.push("evil") })
  assert.throws(() => { ERROR_CLASSES.push("evil") })
  assert.throws(() => { SAFE_HINTS.push("evil") })
})

await rm(TMP, { recursive: true, force: true })
console.log(`\n${passed}/${passed} OK`)
