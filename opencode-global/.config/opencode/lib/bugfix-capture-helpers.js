// bugfix-capture-helpers.js — чистая логика capture-плагина BF-20261010-01 (Phase 1).
import { exec } from "node:child_process"
import { promisify } from "node:util"
// Spec: docs/specs/bugfix-failure-rule.md + docs/specs/bugfix-proactive-plugin.md (S3–S7).
// zero-LLM, metadata-only, fail-closed redaction. Никаких prompt/output/secret/path
// в записях; сырой текст ошибки только входит в классификатор и НЕ сохраняется.
import { appendFile, mkdir, readFile, readdir, rename, stat, writeFile } from "node:fs/promises"
import { existsSync } from "node:fs"
import { join } from "node:path"
import { createHash } from "node:crypto"

// ── Константы-словари (S5/S6/resolutions, фиксированные, не вычисляются) ──

export const ALLOWED_REPOS = Object.freeze([
  "dotfiles", "OpenCode-Vault", "AndroidOS", "ChaT", "recruiting-hr",
  "dv-hub", "SERPlux", "TradingMind",
])

export const ERROR_CLASSES = Object.freeze([
  "tool-fail", "provider-unavailable", "provider-quota", "provider-timeout",
  "permission-blocked", "unknown",
])

export const SOURCE_CLASSES = Object.freeze(["tool", "provider", "permission"])

export const SAFE_HINTS = Object.freeze([
  "bash-error", "edit-error", "read-error", "write-error", "tool-exec-error",
  "provider-quota-429", "provider-balance", "provider-unavailable",
  "provider-timeout", "provider-error-generic",
  "permission-rejected", "classifier-fallback",
])

// S6: рекомендация, не dispatch.
export const RECOMMENDED_ROUTES = Object.freeze({
  "tool-fail": "zone-executor (bash-dev/util-dev/stow-ops)",
  "provider-unavailable": "workflow-retry-then-stop",
  "provider-quota": "workflow-retry-then-stop",
  "provider-timeout": "workflow-retry-then-stop",
  "permission-blocked": "meta-permissions + session-restart",
  unknown: "sysop-report",
})

export const STATE_SUBDIR = "opencode/incidents"
export const ROTATE_BYTES = 1_000_000 // S4: >1 МБ
export const ROTATE_LINES = 5000      // S4: >5000 записей
export const RETENTION_DAYS = 90      // резолюция Рудры 2026-10-07 (3)

// ── Fail-closed детекторы (S7) ──

const SECRET_RE = [
  /sk-[A-Za-z0-9_]{8,}/,
  /gh[pousr]_[A-Za-z0-9]{10,}/,
  /xox[bap]-[A-Za-z0-9-]{10,}/,
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
  /\b(api[_-]?key|token|secret|password|authorization)\b\s*[:=]\s*\S/i,
  /\bbearer\s+[A-Za-z0-9._~+/-]{12,}/i,
]
// puti: absolute unix/win пути (S7: никогда не пишутся); корневые каталоги FHS +
//Manjaro-специфика (nix/snap/opt/srv)
const ABS_PATH_RE = /(^|\s)(~?\/(?:home|root|tmp|etc|var|usr|proc|dev|mnt|media|run|opt|srv|nix|snap|boot|lib|bin|sbin)\b|[A-Za-z]:\\\\?)/

/** @returns {boolean} true, если значение содержит секрет-подобное или absolute path. */
export function detectUnsafe(value) {
  if (value === null || value === undefined) return false
  const s = String(value)
  for (const re of SECRET_RE) if (re.test(s)) return true
  return ABS_PATH_RE.test(s)
}

/**
 * Проверка всех полей перед записью. Возвращает {ok:true} | {ok:false, code}.
 * Бросать наружу ничего не должен: исключение детектора = код DET-FAIL (S7 п.3),
 * без исходного значения в выводе.
 */
export function guardFields(fields) {
  try {
    for (const [k, v] of Object.entries(fields)) {
      if (detectUnsafe(v)) return { ok: false, code: `RED-${k}` }
    }
    return { ok: true }
  } catch {
    return { ok: false, code: "DET-FAIL" }
  }
}

// ── Классификация (S5, детерминированно) ──

const TOOL_HINTS = { bash: "bash-error", edit: "edit-error", read: "read-error", write: "write-error" }

/**
 * @param {"tool"|"provider"|"permission"} source
 * @param {{tool?: string, message?: string, type?: string, status?: number|undefined, reply?: string}} fields
 * @returns {{error_class: string, safe_hint: string}}
 */
export function classifyFailure(source, fields) {
  try {
    if (source === "tool") {
      const t = fields.tool ?? ""
      return { error_class: "tool-fail", safe_hint: TOOL_HINTS[t] ?? "tool-exec-error" }
    }
    if (source === "permission") {
      if (fields.reply === "reject") return { error_class: "permission-blocked", safe_hint: "permission-rejected" }
      return { error_class: "unknown", safe_hint: "classifier-fallback" }
    }
    if (source === "provider") {
      const msg = String(fields.message ?? "")
      const type = String(fields.type ?? "")
      const status = Number(fields.status ?? 0)
      if (status === 429 || /quota|insufficient|rate.?limit/i.test(msg + type))
        return { error_class: "provider-quota", safe_hint: "provider-quota-429" }
      if (/balance|exhausted|credit/i.test(msg)) return { error_class: "provider-quota", safe_hint: "provider-balance" }
      if (/unavailable|not found|no such model/i.test(msg + type))
        return { error_class: "provider-unavailable", safe_hint: "provider-unavailable" }
      if (/timeout|timed.?out|ETIMEDOUT|ECONNRESET|socket hang/i.test(msg + type))
        return { error_class: "provider-timeout", safe_hint: "provider-timeout" }
      return { error_class: "unknown", safe_hint: "provider-error-generic" }
    }
  } catch {
    return { error_class: "unknown", safe_hint: "classifier-fallback" }
  }
  return { error_class: "unknown", safe_hint: "classifier-fallback" }
}

// ── Запись (S4) ──

const SESSION_RE = /^ses_[A-Za-z0-9]+$/

/**
 * Собрать capture-запись. Throws {code} при любой небезопасности (fail-closed):
 * запись НЕ создаётся.
 */
export function buildCapture({ source, projectSlug, sessionID, classified, ts = Math.floor(Date.now() / 1000) }) {
  if (!ERROR_CLASSES.includes(classified.error_class) || !SAFE_HINTS.includes(classified.safe_hint)) {
    throw { code: "BAD-ENUM" }
  }
  if (!SOURCE_CLASSES.includes(source)) throw { code: "BAD-SOURCE" }
  if (typeof sessionID !== "string" || !SESSION_RE.test(sessionID)) throw { code: "BAD-SESSION" }
  if (!ALLOWED_REPOS.includes(projectSlug)) throw { code: "NO-CREATE" } // Scope Guard (S7 п.5)
  const fields = {
    capture_id: createHash("sha256")
      .update(`${projectSlug}|${classified.error_class}|${classified.safe_hint}|${sessionID}|${ts}`)
      .digest("hex")
      .slice(0, 16),
    ts,
    error_class: classified.error_class,
    source_class: source,
    session_id: sessionID,
    project_slug: projectSlug,
    safe_hint: classified.safe_hint,
  }
  const g = guardFields(fields)
  if (!g.ok) throw { code: g.code }
  return {
    ...fields,
    correlation_id: correlationId(projectSlug, classified.error_class, classified.safe_hint),
    recommended_route: RECOMMENDED_ROUTES[classified.error_class] ?? "sysop-report",
  }
}

export function correlationId(projectSlug, errorClass, safeHint) {
  return createHash("sha256").update(`${projectSlug}|${errorClass}|${safeHint}`).digest("hex").slice(0, 24)
}

export function projectSlugFromDir(directory) {
  if (typeof directory !== "string" || !directory) return ""
  const parts = directory.replace(/[/\\]+$/, "").split(/[/\\]/)
  return parts[parts.length - 1] ?? ""
}

// ── Phase 2 (Route) и Phase 3 (Notify) — BF-20261010-01 ──

/**
 * Phase 3: системное уведомление через notify-send (dunst). Только safe_hint,
 * никаких raw-значений (те же ограничения, что и у записи).
 */
export async function notifyUser(title, message) {
  try {
    const execAsync = promisify(exec)
    const cleanTitle = String(title).replace(/"/g, '\\"')
    const cleanMsg = String(message).replace(/"/g, '\\"')
    await execAsync(`notify-send "${cleanTitle}" "${cleanMsg}"`)
  } catch {
    console.error("[bugfix-capture] notify-send failed")
  }
}

/**
 * Phase 2: заявка в очередь pending/ для асинхронного разбора (/bugfix).
 * Payload — metadata-only (та же запись, что в журнале).
 */
export async function routeIncident(stateDir, record) {
  try {
    const pendingDir = join(stateDir, "pending")
    await mkdir(pendingDir, { recursive: true })
    const taskFile = join(pendingDir, `${record.capture_id}.json`)
    await writeFile(taskFile, JSON.stringify(record, null, 2))
  } catch {
    console.error("[bugfix-capture] routeIncident failed")
  }
}

// ── LedgerAppend (dedup по correlation_id в окне; атомарная запись tmp+rename — урок T-180) ──

function slugFile(stateDir, slug) {
  return join(stateDir, `${slug}.djsonl`)
}
function indexPath(stateDir) {
  return join(stateDir, "incidents-index.jsonl")
}

async function readJsonl(path) {
  if (!existsSync(path)) return []
  const out = []
  for (const line of (await readFile(path, "utf-8")).split("\n")) {
    const t = line.trim()
    if (!t) continue
    try { out.push(JSON.parse(t)) } catch { /* повреждённая строка — пропускаем */ }
  }
  return out
}

async function writeJsonlAtomic(path, lines) {
  const tmp = `${path}.tmp-${process.pid}`
  await writeFile(tmp, jsonlSerialize(lines))
  await rename(tmp, path)
}
function jsonlSerialize(items) {
  return items.map((i) => JSON.stringify(i)).join("\n") + (items.length ? "\n" : "")
}

/** Ротация >1МБ или >5000 строк → _archive/. Возвращает true, если ротация случилась. */
async function maybeRotate(path, archiveDir, now = Date.now()) {
  if (!existsSync(path)) return false
  const st = await stat(path)
  let need = st.size > ROTATE_BYTES
  if (!need) {
    const lines = await readFile(path, "utf-8")
    need = lines.split("\n").filter((l) => l.trim()).length > ROTATE_LINES
  }
  if (!need) return false
  await mkdir(archiveDir, { recursive: true })
  const stamp = new Date(now).toISOString().replace(/[:.]/g, "-")
  await rename(path, join(pathDirOf(path), "_archive", `${baseNameOf(path)}.${stamp}`))
  return true
}
function pathDirOf(p) { return p.slice(0, p.lastIndexOf("/")) }
function baseNameOf(p) { return p.slice(p.lastIndexOf("/") + 1) }

/** Retention 90 дней: state-файлы старше — в _archive/ (секреты не архивируются — их и так нет). */
export async function applyRetention(stateDir, now = Date.now()) {
  if (!existsSync(stateDir)) return
  await mkdir(join(stateDir, "_archive"), { recursive: true })
  for (const name of await readdir(stateDir)) {
    if (name === "_archive" || !name.endsWith(".djsonl")) continue
    const full = join(stateDir, name)
    const st = await stat(full)
    if (now - st.mtimeMs > RETENTION_DAYS * 86_400_000) {
      await rename(full, join(stateDir, "_archive", name))
    }
  }
}

/**
 * Добавить capture: дедуп по correlation_id в окне сессии (count++, last_ts),
 * иначе новая строка. Возвращает {action: "new"|"counted", record|entry}.
 */
export async function appendCapture(stateDir, record) {
  await mkdir(stateDir, { recursive: true })
  await applyRetention(stateDir)
  const file = slugFile(stateDir, record.project_slug)
  await maybeRotate(file, join(stateDir, "_archive"))
  const lines = await readJsonl(file)
  const idx = lines.findIndex((l) => l.project_slug === record.project_slug && l.correlation_id === record.correlation_id && l.session_id === record.session_id)
  let entry
  let action
  if (idx >= 0) {
    entry = { ...lines[idx], count: (lines[idx].count ?? 1) + 1, last_ts: record.ts }
    lines[idx] = entry
    action = "counted"
  } else {
    entry = { ...record, count: 1, first_ts: record.ts, last_ts: record.ts }
    lines.push(entry)
    action = "new"
  }
  await writeJsonlAtomic(file, lines)
  // агрегат поперек сессий: одна строка на correlation_id (S12.5)
  const ipath = indexPath(stateDir)
  await maybeRotate(ipath, join(stateDir, "_archive"))
  const idxLines = await readJsonl(ipath)
  const ii = idxLines.findIndex((l) => l.correlation_id === record.correlation_id)
  if (ii >= 0) {
    idxLines[ii] = {
      ...idxLines[ii],
      count: idxLines[ii].count + (action === "counted" ? 1 : 1),
      last_ts: record.ts,
      sessions: [...new Set([...(idxLines[ii].sessions ?? []), record.session_id])],
    }
  } else {
    idxLines.push({
      correlation_id: record.correlation_id,
      project_slug: record.project_slug,
      error_class: record.error_class,
      safe_hint: record.safe_hint,
      recommended_route: record.recommended_route,
      first_ts: record.ts,
      last_ts: record.ts,
      count: 1,
      sessions: [record.session_id],
    })
  }
  await writeJsonlAtomic(ipath, idxLines)
  return { action, entry }
}
