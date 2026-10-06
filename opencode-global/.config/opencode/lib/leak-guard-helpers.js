// leak-guard-helpers.js
// Pure helpers for the leak-guard plugin: collect known secrets from local
// OpenCode storages (password / auth tokens) and redact them from tool
// outputs via exact-match replacement (split/join, no regex). Shared
// between the plugin (~/.config/opencode/plugins/leak-guard.ts) and the
// offline fixture tests (leak-guard-helpers.test.mjs). Runtime deps:
// только node:fs/node:os/node:path, без сети, без побочных эффектов на
// import.
//
// Storages (defaults, override via SECRET_GUARD_PATHS env for tests):
//   1) ~/.config/opencode/service.json    — поле "password"
//   2) ~/.local/share/opencode/auth.json  — все строковые значения
//   3) ~/.local/state/opencode/service.json — поле "password"
//
// Env knobs:
//   SECRET_GUARD_MIN_LENGTH — минимальная длина секрета (default 12);
//   SECRET_GUARD_PATHS      — CSV список путей (override defaults, все
//                             трактуется как "all-strings" для тестов).
//
// Приватность: collected secrets НЕ логируются и не печатаются — только
// длина/количество может появляться в диагностике. Redaction применяется
// к выводимым строкам до отправки модели.
//
// Fail-safe: отсутствующие/битые файлы стораджей не роняют сбор —
// collectKnownSecrets() возвращает [] без throw.

import { existsSync, readFileSync, statSync } from "node:fs"
import { homedir } from "node:os"
import { join } from "node:path"

export const REDACT_REPLACEMENT = "[REDACTED]"
export const DEFAULT_MIN_LENGTH = 12

const DEFAULT_PATHS = [
  { path: join(homedir(), ".config/opencode/service.json"), field: "password" },
  { path: join(homedir(), ".local/share/opencode/auth.json"), field: "all-strings" },
  { path: join(homedir(), ".local/state/opencode/service.json"), field: "password" },
]

function parsePathsEnv(value) {
  if (typeof value !== "string" || value.trim() === "") return null
  return value
    .split(",")
    .map((p) => ({ path: p.trim(), field: "all-strings" }))
    .filter((e) => e.path.length > 0)
}

function resolveMinLength(opts) {
  if (opts != null && Number.isFinite(opts.minLength) && opts.minLength > 0) {
    return opts.minLength
  }
  const env = process.env.SECRET_GUARD_MIN_LENGTH
  if (env !== undefined) {
    const n = Number(env)
    if (Number.isFinite(n) && n > 0) return n
  }
  return DEFAULT_MIN_LENGTH
}

function extractField(obj, field) {
  if (obj == null || typeof obj !== "object" || Array.isArray(obj)) return []
  if (field === "password") {
    const v = obj.password
    return typeof v === "string" && v.length > 0 ? [v] : []
  }
  if (field === "all-strings") {
    const out = []
    for (const v of Object.values(obj)) {
      if (typeof v === "string" && v.length > 0) out.push(v)
      // Вложенные объекты не обходим: стораджи flat по спеку.
    }
    return out
  }
  return []
}

// Собрать известные секреты из стораджей. Возвращает массив уникальных
// строк длиной >= minLength. Fail-safe: отсутствие/битость файлов → [].
export function collectKnownSecrets(opts = {}) {
  const minLength = resolveMinLength(opts)
  const pathsOverride = parsePathsEnv(process.env.SECRET_GUARD_PATHS)
  let sources
  if (Array.isArray(opts.paths) && opts.paths.length > 0) {
    // opts.paths — для тестов: каждый путь трактуется как "all-strings".
    sources = opts.paths
      .filter((p) => typeof p === "string" && p.length > 0)
      .map((p) => ({ path: p, field: "all-strings" }))
  } else if (pathsOverride !== null) {
    sources = pathsOverride
  } else {
    sources = DEFAULT_PATHS
  }
  const seen = new Set()
  const out = []
  for (const src of sources) {
    try {
      if (!existsSync(src.path)) continue
      const text = readFileSync(src.path, "utf8")
      let parsed
      try {
        parsed = JSON.parse(text)
      } catch {
        continue
      }
      for (const secret of extractField(parsed, src.field)) {
        if (typeof secret !== "string") continue
        if (secret.length < minLength) continue
        if (seen.has(secret)) continue
        seen.add(secret)
        out.push(secret)
      }
    } catch {
      // Fail-safe: IO/parse ошибки не роняют сбор.
    }
  }
  return out
}

// Exact-match redaction: split/join, без regex. Длинные секреты
// обрабатываются раньше коротких (сортировка по убыванию длины), чтобы
// избежать частичных замен при отношении префикса.
export function redactExact(text, secrets) {
  if (typeof text !== "string" || text.length === 0) return text
  if (!Array.isArray(secrets) || secrets.length === 0) return text
  const ordered = secrets
    .filter((s) => typeof s === "string" && s.length > 0)
    .sort((a, b) => b.length - a.length)
  if (ordered.length === 0) return text
  let out = text
  for (const secret of ordered) {
    out = out.split(secret).join(REDACT_REPLACEMENT)
  }
  return out
}

// --- Cache-invalidation helpers (mtime+size snapshot) -----------------------
//
// Чтобы плагин не пересобирал секреты на каждом turn, но и не носил
// устаревший набор после ротации пароля, держим снимок mtime+size по
// каждому source-файлу. Пересбор запускается, когда (a) прошёл хотя бы
// minIntervalMs с последней проверки И (b) снимок изменился.
// Ошибки stat не роняют — проблемный путь считается "непрочитанным",
// что триггерит пересбор (fail-safe в сторону более частых чтений).

function statEntry(path) {
  try {
    const st = statSync(path)
    return { mtimeMs: Number(st.mtimeMs) || 0, size: Number(st.size) || 0 }
  } catch {
    return null
  }
}

function buildSnapshot(paths) {
  const m = new Map()
  for (const p of paths) m.set(p, statEntry(p))
  return m
}

function snapshotEqual(a, b) {
  if (a.size !== b.size) return false
  for (const [k, va] of a) {
    const vb = b.get(k)
    if (va === null && vb === null) continue
    if (va === null || vb === null) return false
    if (va.mtimeMs !== vb.mtimeMs || va.size !== vb.size) return false
  }
  return true
}

// Резолвит те же пути, что будет читать collectKnownSecrets — чтобы
// плагин мог строить снимок без дублирования логики.
export function resolveSecretPaths(opts = {}) {
  const pathsOverride = parsePathsEnv(process.env.SECRET_GUARD_PATHS)
  if (Array.isArray(opts.paths) && opts.paths.length > 0) {
    return opts.paths.filter((p) => typeof p === "string" && p.length > 0)
  }
  if (pathsOverride !== null) return pathsOverride.map((s) => s.path)
  return DEFAULT_PATHS.map((s) => s.path)
}

// Stateful collector: кэширует последний набор секретов и перечитывает
// стораджи только когда (a) прошёл minIntervalMs с последней проверки
// и (b) mtime/size какого-то источника изменились. Ошибки не бросаются,
// возвращается предыдущий кэш (или []).
export function createSecretsCollector(opts = {}) {
  const minIntervalMs =
    Number.isFinite(opts.minIntervalMs) && opts.minIntervalMs >= 0
      ? opts.minIntervalMs
      : 5000
  const collectOpts = { paths: opts.paths, minLength: opts.minLength }
  const paths = resolveSecretPaths(collectOpts)
  let cachedSecrets = null
  let cachedSnapshot = null
  let lastCheckTs = 0

  function refresh() {
    const now = Date.now()
    if (cachedSecrets !== null && now - lastCheckTs < minIntervalMs) {
      return cachedSecrets
    }
    lastCheckTs = now
    const snap = buildSnapshot(paths)
    if (cachedSnapshot !== null && snapshotEqual(cachedSnapshot, snap)) {
      return cachedSecrets ?? []
    }
    cachedSnapshot = snap
    try {
      cachedSecrets = collectKnownSecrets(collectOpts)
    } catch {
      cachedSecrets = []
    }
    return cachedSecrets ?? []
  }

  return {
    getSecrets: refresh,
    invalidate() {
      cachedSnapshot = null
      lastCheckTs = 0
    },
  }
}

// Auto-discovery guard (конвенция lib/): callable default без побочных
// эффектов, чтобы каталог lib/ мог грузиться как pseudo-plugin.
export default Object.assign(async () => ({}), {
  REDACT_REPLACEMENT,
  DEFAULT_MIN_LENGTH,
  collectKnownSecrets,
  redactExact,
  resolveSecretPaths,
  createSecretsCollector,
})
