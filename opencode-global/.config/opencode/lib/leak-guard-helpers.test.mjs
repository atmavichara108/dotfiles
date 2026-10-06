#!/usr/bin/env node
// leak-guard-helpers.test.mjs — offline fixture-тесты leak-guard.
// Запуск: node opencode-global/.config/opencode/lib/leak-guard-helpers.test.mjs
// Только встроенные модули node (assert/fs/path/url), без сети и внешних
// зависимостей. Пишет ТОЛЬКО во временные fixture-пути /tmp/opencode/
// leak-guard-test-* — реальные стораджи НЕ читаются.
//
// Все "секреты" ниже — ФИКТИВНЫЕ, только для проверки redaction.
//
// Main-guard: тесты выполняются только при прямом запуске (`node <file>`).
// При auto-discovery-импорте (если lib/ грузится как каталог плагинов)
// модуль безвреден: callable default-экспорт и ноль побочных эффектов —
// та же конвенция, что у остальных модулей lib/.

import assert from "node:assert/strict"
import { existsSync, mkdirSync, realpathSync, rmSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { fileURLToPath } from "node:url"
import { collectKnownSecrets, redactExact } from "./leak-guard-helpers.js"

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
    tmpRoot = join(
      "/tmp/opencode",
      `leak-guard-test-${process.pid}-${Date.now()}`,
    )
    rmSync(tmpRoot, { recursive: true, force: true })
    mkdirSync(tmpRoot, { recursive: true })
  }
  return tmpRoot
}

const tests = []
function test(name, fn) {
  tests.push({ name, fn })
}

function writeFixture(filename, payload) {
  const dir = join(tmp(), "storages")
  mkdirSync(dir, { recursive: true })
  const p = join(dir, filename)
  writeFileSync(p, JSON.stringify(payload), "utf8")
  return p
}

function withEnv(overrides, fn) {
  const prev = Object.create(null)
  for (const [k, v] of Object.entries(overrides)) {
    prev[k] = process.env[k]
    if (v === undefined) delete process.env[k]
    else process.env[k] = v
  }
  try {
    return fn()
  } finally {
    for (const [k, v] of Object.entries(prev)) {
      if (v === undefined) delete process.env[k]
      else process.env[k] = v
    }
  }
}

// --- 1. Сбор секретов -------------------------------------------------------

test("collect: password field is collected", () => {
  const p = writeFixture("svc-password.json", {
    password: "SUPER_SECRET_PASSWORD_12345",
    other: "keep",
  })
  const secrets = collectKnownSecrets({ paths: [p] })
  assert.ok(secrets.includes("SUPER_SECRET_PASSWORD_12345"))
  assert.ok(!secrets.includes("keep")) // non-string filter не применим, но "keep" короткий (4 < 12)
})

test("collect: all string values from auth-like storage", () => {
  const p = writeFixture("auth.json", {
    provider: "openai",
    api_key: "FAKE_LONG_API_KEY_VALUE_99",
    auth: "LONG_BEARER_TOKEN_VALUE_XYZ",
  })
  const secrets = collectKnownSecrets({ paths: [p], minLength: 6 })
  // "openai" (6) — попадает при minLength=6
  assert.ok(secrets.includes("openai"))
  assert.ok(secrets.includes("FAKE_LONG_API_KEY_VALUE_99"))
  assert.ok(secrets.includes("LONG_BEARER_TOKEN_VALUE_XYZ"))
})

test("collect: missing storages → [] (no throw)", () => {
  const secrets = collectKnownSecrets({
    paths: [join(tmp(), "nonexistent-1.json"), join(tmp(), "nonexistent-2.json")],
  })
  assert.deepEqual(secrets, [])
})

test("collect: malformed JSON in a storage → skipped (no throw)", () => {
  const dir = join(tmp(), "broken")
  mkdirSync(dir, { recursive: true })
  const p = join(dir, "broken.json")
  writeFileSync(p, "{not valid json at all", "utf8")
  const secrets = collectKnownSecrets({ paths: [p] })
  assert.deepEqual(secrets, [])
})

test("collect: min-length filter excludes short values", () => {
  const p = writeFixture("mixed.json", { a: "SHORT", b: "LONG_ENOUGH_SECRET_12345678" })
  const withDefault = collectKnownSecrets({ paths: [p], minLength: 12 })
  assert.ok(!withDefault.includes("SHORT"))
  assert.ok(withDefault.includes("LONG_ENOUGH_SECRET_12345678"))
  const withLow = collectKnownSecrets({ paths: [p], minLength: 3 })
  assert.ok(withLow.includes("SHORT"))
  assert.ok(withLow.includes("LONG_ENOUGH_SECRET_12345678"))
})

test("collect: dedupes same secret from multiple storages", () => {
  const secret = "SAME_SECRET_ACROSS_FILES_X"
  const p1 = writeFixture("dup-1.json", { password: secret })
  const p2 = writeFixture("dup-2.json", { token: secret })
  const secrets = collectKnownSecrets({ paths: [p1, p2] })
  assert.equal(secrets.filter((s) => s === secret).length, 1)
})

test("collect: env SECRET_GUARD_PATHS overrides defaults", () => {
  const secret = "ENV_GUARD_PATHS_TEST_SECRET"
  const p = writeFixture("env-test.json", { key: secret })
  const r = withEnv({ SECRET_GUARD_PATHS: p, SECRET_GUARD_MIN_LENGTH: "6" }, () =>
    collectKnownSecrets(),
  )
  assert.ok(r.includes(secret))
})

test("collect: env SECRET_GUARD_MIN_LENGTH is respected", () => {
  const secret = "TWELVECHARS1" // 12 символов
  const p = writeFixture("env-min.json", { v: secret })
  const excluded = withEnv({ SECRET_GUARD_MIN_LENGTH: "13" }, () =>
    collectKnownSecrets({ paths: [p] }),
  )
  assert.ok(!excluded.includes(secret))
  const included = withEnv({ SECRET_GUARD_MIN_LENGTH: "12" }, () =>
    collectKnownSecrets({ paths: [p] }),
  )
  assert.ok(included.includes(secret))
})

test("collect: defaults do not throw even if real storages are absent", () => {
  // Без fixture — просто вызываем с дефолтами. Если какой-то сторадж
  // отсутствует, это НЕ должно бросать.
  const secrets = collectKnownSecrets()
  assert.ok(Array.isArray(secrets))
})

// --- 2. Exact redaction -----------------------------------------------------

test("redactExact: known secret is replaced with [REDACTED]", () => {
  const secret = "SUPER_SECRET_VALUE_12345"
  const p = writeFixture("svc1.json", { password: secret })
  const secrets = collectKnownSecrets({ paths: [p] })
  assert.equal(redactExact(`used ${secret} here`, secrets), "used [REDACTED] here")
})

test("redactExact: multiple occurrences are all replaced", () => {
  const secret = "MULTI_OCCURRENCE_SECRET_X"
  const p = writeFixture("multi.json", { password: secret })
  const secrets = collectKnownSecrets({ paths: [p] })
  assert.equal(
    redactExact(`${secret} and ${secret} again`, secrets),
    "[REDACTED] and [REDACTED] again",
  )
})

test("redactExact: similar-but-not-matching string is untouched", () => {
  const secret = "EXACT_PASSWORD_0000001"
  const p = writeFixture("svc2.json", { password: secret })
  const secrets = collectKnownSecrets({ paths: [p] })
  const similar = "EXACT_PASSWORD_0000002" // отличается последним символом
  assert.equal(redactExact(`x ${similar} y`, secrets), `x ${similar} y`)
  // И префикс секрета — тоже не матчится (точное сравнение).
  const prefix = secret.slice(0, -2)
  assert.equal(redactExact(`x ${prefix} y`, secrets), `x ${prefix} y`)
})

test("redactExact: JSON string stays valid after redaction", () => {
  const secret = "AUTH_JSON_SECRET_VALUE_X"
  const p = writeFixture("auth.json", { key: secret })
  const secrets = collectKnownSecrets({ paths: [p] })
  const original = JSON.stringify({ password: secret, message: "hello", count: 42 })
  const redacted = redactExact(original, secrets)
  // redacted должен остаться валидным JSON: secret — строка, [REDACTED] —
  // строка, замена в JSON-строковом значении не ломает структуру.
  const parsed = JSON.parse(redacted)
  assert.equal(parsed.password, "[REDACTED]")
  assert.equal(parsed.message, "hello")
  assert.equal(parsed.count, 42)
})

test("redactExact: two secrets with prefix relationship — longer wins first", () => {
  const short = "ABCDEFGH1234"
  const long = "ABCDEFGH1234_EXTENDED"
  const p = writeFixture("two.json", { a: short, b: long })
  const secrets = collectKnownSecrets({ paths: [p], minLength: 6 })
  assert.ok(secrets.includes(short))
  assert.ok(secrets.includes(long))
  // Длинный должен замениться целиком, не частично.
  const out = redactExact(`x ${long} y ${short} z`, secrets)
  assert.equal(out, "x [REDACTED] y [REDACTED] z")
})

test("redactExact: empty secrets list → text unchanged", () => {
  assert.equal(redactExact("hello world", []), "hello world")
  assert.equal(redactExact("hello world", null), "hello world")
})

test("redactExact: non-string input → returned as-is", () => {
  assert.equal(redactExact("", ["x"]), "")
  assert.equal(redactExact(null, ["x"]), null)
  assert.equal(redactExact(undefined, ["x"]), undefined)
})

// --- runner ------------------------------------------------------------------

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
  console.log(`leak-guard-helpers tests: ${passed}/${tests.length} passed`)
  return failed.length === 0 ? 0 : 1
}

// Auto-discovery guard: callable default, без побочных эффектов.
export default async () => ({})

if (isMain) {
  process.exitCode = run()
  if (tmpRoot !== undefined) rmSync(tmpRoot, { recursive: true, force: true })
}
