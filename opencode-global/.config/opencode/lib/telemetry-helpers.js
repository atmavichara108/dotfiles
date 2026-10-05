// telemetry-helpers.js
// Pure helpers for the telemetry plugin (T-124 Telemetry P0, ECO-002):
// audit-log (metadata-only JSONL) + token-budget (учёт и отчёты по токенам).
// Shared between the plugin (~/.config/opencode/plugins/telemetry.ts) and the
// offline fixture tests (telemetry-helpers.test.mjs). Runtime deps: только
// node:fs/node:path, без сети, без побочных эффектов на import.
//
// Приватность (T-124 §3) — четыре слоя:
//   1) buildAuditRecord берёт из input ТОЛЬКО известные поля (action,
//      session_id, task_id, duration_ms, details) — промпты/контент/лишние
//      ключи отбрасываются до сериализации;
//   2) content-подобные ключи в details (prompt/messages/content/stdout/
//      note/...) вырезаются: значение → [REDACTED], ключ остаётся маркером;
//      строковые значения длиннее 160 символов обрезаются (…[TRUNCATED]),
//      глубже 8 уровней вложенности значения заменяются на [REDACTED];
//   3) все строковые поля проходят redaction по паттернам sk- / Bearer /
//      api_key / password / token=;
//   4) appendJsonlRecord делает финальный redaction-проход по сериализованной
//      строке (защита в глубину для прямых вызовов).
//
// Append-only (T-124 §3): логи только дозаписываются в конец (fs append),
// исторические записи никогда не читаются-переписываются. Битый хвост
// (недописанная последняя строка) не чинится — новая запись отделяется \n.

import { appendFileSync, closeSync, existsSync, mkdirSync, openSync, readFileSync, readSync, statSync } from "node:fs"
import { dirname } from "node:path"

// --- Redaction (T-124 §3) ----------------------------------------------------

// Единообразная замена для всех совпадений.
export const REDACT_REPLACEMENT = "[REDACTED]"

// Пять паттернов из спеки §3. Charset значения не содержит " ' \ , \n —
// совпадение не может пересечь границу JSON-строки, поэтому финальный проход
// по сериализованной строке не ломает JSON.
export const REDACT_PATTERNS = [
  // `sk-` — API-ключи (OpenAI/Anthropic-стиль); ≥6 символов после префикса
  /\bsk-[a-z0-9_-]{6,}/gi,
  // `Bearer ` — bearer-токен целиком
  /\bbearer\s+[a-z0-9._~+/=-]+/gi,
  // `api_key` (также api-key / api key) — ключевое слово, при возможности
  // вместе со значением: после = / : / "key": "value" значение — одиночный
  // токен (без пробелов); после чистого пробела (prose-форма "password is
  // ...") — жадно до первого стоп-символа, чтобы хвост секрета не утёк
  /\bapi[\s_-]?key\b(?:(?:["']?\s*[=:]\s*["']?[^\s,;"'\\]*)|(?:\s+[^\n,;"'\\]*))?/gi,
  // `password` — аналогично
  /\bpassword\b(?:(?:["']?\s*[=:]\s*["']?[^\s,;"'\\]*)|(?:\s+[^\n,;"'\\]*))?/gi,
  // `token=` — только с разделителем (= или :), чтобы не резать легитимные
  // "token count" / "token_budget" / input_tokens; prose-форма не матчится
  // сознательно (ложные срабатывания на учётных метаданных)
  /\btoken\b(?:["']?\s*[=:]\s*["']?[^\s,;"'\\]*)/gi,
]

// Точные имена ключей-секретов: ключ И значение заменяются на [REDACTED].
// Exact-match, чтобы input_tokens/output_tokens (учёт токенов) не вырезались.
export const SECRET_KEY_RE = /^(?:api[\s_-]?key|api[\s_-]?token|access[\s_-]?token|auth|authorization|bearer|passwd|password|pwd|secret|token)$/i

// Точные имена ключей-«контента» (промпт/ответ/сообщение/поток вывода):
// значение — содержимое, оно не логируется никогда (T-124 §3). Ключ остаётся
// маркером. review: +system/reply/answer/stdout/stderr/arguments/result/
// history/transcript/summary/note.
export const CONTENT_KEY_RE = /^(?:answer|arguments|completion|completions|content|contents|data|history|input|inputs|message|messages|note|output|outputs|prompt|prompts|reply|response|responses|result|stdout|stderr|summary|system|text|transcript)$/i

// Cap на длину строковых значений в details: metadata-лог, а не хранилище
// контента. Обрезка применяется ДО redaction-проходов и только к details
// (redactFields) — сами поля записи (ts/ids/action) не трогаются.
export const DETAILS_MAX_CHARS = 160
export const TRUNCATION_MARKER = "…[TRUNCATED]"

function capDetailsString(text) {
  if (typeof text !== "string" || text.length <= DETAILS_MAX_CHARS) return text
  let cut = DETAILS_MAX_CHARS
  // Не рвать суррогатную пару на границе обрезки (валидность строки/JSON).
  const boundary = text.charCodeAt(cut - 1)
  if (boundary >= 0xd800 && boundary <= 0xdbff) cut -= 1
  return text.slice(0, cut) + TRUNCATION_MARKER
}

// Redact секреты по паттернам. Возвращает новую строку (или исходное значение,
// если это не строка).
export function redactString(text) {
  if (typeof text !== "string" || text.length === 0) return text
  let out = text
  for (const pattern of REDACT_PATTERNS) out = out.replace(pattern, REDACT_REPLACEMENT)
  return out
}

// Глубокая копия значения с redaction: строки → обрезка по cap → redactString;
// объекты — секретные ключи целиком → [REDACTED], content-ключи → значение
// [REDACTED]. Глубже 8 уровней вложенности значения не проходят вовсе —
// заменяются на [REDACTED] (контент не должен прятаться в глубине).
// Возвращает новый объект, input не мутируется.
export function redactFields(value, depth = 0) {
  if (value == null) return value
  if (depth > 8) return REDACT_REPLACEMENT
  if (typeof value === "string") return redactString(capDetailsString(value))
  if (Array.isArray(value)) return value.map((item) => redactFields(item, depth + 1))
  if (typeof value === "object") {
    const out = {}
    for (const [key, val] of Object.entries(value)) {
      if (SECRET_KEY_RE.test(key)) {
        out[REDACT_REPLACEMENT] = REDACT_REPLACEMENT
        continue
      }
      if (CONTENT_KEY_RE.test(key)) {
        out[key] = REDACT_REPLACEMENT
        continue
      }
      out[key] = redactFields(val, depth + 1)
    }
    return out
  }
  return value
}

// --- общие утилиты -------------------------------------------------------------

function toIso(now) {
  const date = now === undefined ? new Date() : new Date(now)
  return date.toISOString() // RangeError на невалидной дате — ловит caller
}

function pickString(value) {
  return typeof value === "string" && value.length > 0 ? value : undefined
}

function pickNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined
}

// --- audit-log -----------------------------------------------------------------

// Запись аудит-лога: из input берутся ТОЛЬКО известные поля — всё остальное
// (промпты, контент, лишние ключи) отбрасывается. Строковые поля проходят
// redaction. Порядок ключей фиксирован → детерминированная сериализация.
export function buildAuditRecord(input, now) {
  const src = input != null && typeof input === "object" && !Array.isArray(input) ? input : {}
  const record = {
    ts: toIso(now),
    session_id: pickString(src.session_id),
    task_id: pickString(src.task_id),
    action: pickString(src.action),
    duration_ms: pickNumber(src.duration_ms),
    details:
      src.details != null && typeof src.details === "object"
        ? redactFields(src.details)
        : undefined,
  }
  // Строковые поля — через redaction-фильтр (T-124 §3: ВСЕ строковые поля).
  if (record.session_id !== undefined) record.session_id = redactString(record.session_id)
  if (record.task_id !== undefined) record.task_id = redactString(record.task_id)
  if (record.action !== undefined) record.action = redactString(record.action)
  for (const key of Object.keys(record)) {
    if (record[key] === undefined) delete record[key]
  }
  return record
}

// --- token-budget ---------------------------------------------------------------

// Детерминированная оценка: ~4 символа на токен.
export function estimateTokens(text) {
  if (typeof text !== "string") return 0
  return Math.ceil(text.length / 4)
}

function pickTokens(value) {
  if (value === undefined) return 0
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error("token-budget record: token counts must be non-negative numbers")
  }
  return value
}

// Запись учёта токенов. Явные input_tokens/output_tokens имеют приоритет над
// text-оценкой; text-оценка помечается estimated: true. Сам text НЕ
// записывается никогда — только оценка. Порядок ключей фиксирован.
export function buildTokenRecord(input, now) {
  const src = input != null && typeof input === "object" && !Array.isArray(input) ? input : {}
  const session_id = pickString(src.session_id)
  if (session_id === undefined) {
    throw new Error('token-budget record: "session_id" (string) is required')
  }
  const model = pickString(src.model)

  const hasInput = typeof src.input_tokens === "number"
  const hasOutput = typeof src.output_tokens === "number"
  const hasText = typeof src.text === "string" && src.text.length > 0

  let input_tokens
  let output_tokens
  let estimated = false
  if (hasInput || hasOutput) {
    input_tokens = pickTokens(src.input_tokens)
    output_tokens = pickTokens(src.output_tokens)
  } else if (hasText) {
    input_tokens = estimateTokens(src.text)
    output_tokens = 0
    estimated = true
  } else {
    throw new Error("token-budget record: provide input_tokens/output_tokens (numbers) or text (string)")
  }

  const record = { ts: toIso(now), session_id: redactString(session_id) }
  if (model !== undefined) record.model = redactString(model)
  record.input_tokens = input_tokens
  record.output_tokens = output_tokens
  record.estimated = estimated
  return record
}

// --- append-only JSONL storage ---------------------------------------------------

// Дозапись одной JSON-строки в конец лога. Каталог создаётся (recursive),
// отсутствующий файл создаётся. Существующие байты не переписываются — только
// fs append. Если хвост файла не завершён \n (битая недописанная строка),
// новая запись ОТДЕЛЯЕТСЯ ведущим \n: история не чинится и не портится, новая
// строка остаётся парсабельной. Возврат: число дописанных байт.
export function appendJsonlRecord(path, record) {
  if (typeof path !== "string" || path.length === 0) {
    throw new Error("appendJsonlRecord: path (string) is required")
  }
  mkdirSync(dirname(path), { recursive: true })

  // Финальный redaction-проход по сериализованной строке (защита в глубину
  // для прямых вызовов): паттерны не пересекают границу JSON-строки, строка
  // остаётся валидным JSON.
  const line = redactString(JSON.stringify(record))
  if (typeof line !== "string") {
    throw new Error("appendJsonlRecord: record is not JSON-serializable")
  }

  const size = existsSync(path) ? statSync(path).size : 0
  const prefix = size > 0 && !endsWithNewline(path, size) ? "\n" : ""
  const chunk = prefix + line + "\n"
  appendFileSync(path, chunk, "utf8")
  return Buffer.byteLength(chunk, "utf8")
}

function endsWithNewline(path, size) {
  const fd = openSync(path, "r")
  try {
    const last = Buffer.alloc(1)
    const read = readSync(fd, last, 0, 1, size - 1)
    return read === 1 && last[0] === 0x0a
  } finally {
    closeSync(fd)
  }
}

// Чтение лога в массив сырых строк (без парсинга): отсутствующий файл → [];
// завершающий \n отбрасывается; внутренние строки — как есть, включая битые
// (их считает и пропускает buildReport).
export function readJsonlLines(path) {
  if (typeof path !== "string" || path.length === 0 || !existsSync(path)) return []
  const text = readFileSync(path, "utf8")
  if (text === "") return []
  const lines = text.split("\n")
  if (lines.length > 0 && lines[lines.length - 1] === "") lines.pop()
  return lines
}

// --- детерминированный отчёт ------------------------------------------------------

const PERIOD_MS = { day: 24 * 60 * 60 * 1000, week: 7 * 24 * 60 * 60 * 1000, all: Infinity }

// Детерминированный отчёт из лога: один и тот же лог (+ одни opts) →
// байт-в-байт одинаковый текст. Никакого Date.now() внутри: опорное время
// берётся из записей (max ts) или явно из opts.now. Битые строки пропускаются
// и считаются. Периоды: day/week — скользящее окно 24h/168h от опорного
// времени; all — весь лог. При превышении opts.threshold отчёт НАЧИНАЕТСЯ
// строкой WARNING.
export function buildReport(lines, period, opts = {}) {
  if (period !== "day" && period !== "week" && period !== "all") {
    throw new Error('buildReport: period must be "day", "week" or "all"')
  }
  const options = opts == null ? {} : opts

  const parsed = []
  let malformed = 0
  const source = Array.isArray(lines) ? lines : []
  for (const raw of source) {
    if (typeof raw !== "string" || raw.trim() === "") continue
    try {
      const obj = JSON.parse(raw)
      if (obj != null && typeof obj === "object" && !Array.isArray(obj)) parsed.push(obj)
      else malformed++
    } catch {
      malformed++
    }
  }

  // Опорное время: явно из opts.now (ISO-строка или мс) или max ts по записям.
  let refMs
  if (options.now !== undefined && options.now !== null) {
    refMs = typeof options.now === "number" ? options.now : Date.parse(options.now)
    if (!Number.isFinite(refMs)) throw new Error("buildReport: opts.now must be a valid date")
  } else {
    let max = NaN
    for (const record of parsed) {
      const ts = Date.parse(record.ts)
      if (Number.isFinite(ts) && (Number.isNaN(max) || ts > max)) max = ts
    }
    refMs = Number.isNaN(max) ? 0 : max
  }

  const windowMs = PERIOD_MS[period]
  const hasSessionFilter = typeof options.sessionId === "string" && options.sessionId.length > 0
  const inPeriod = []
  for (const record of parsed) {
    if (hasSessionFilter && (typeof record.session_id !== "string" || record.session_id !== options.sessionId)) continue
    if (period !== "all") {
      const ts = Date.parse(record.ts)
      if (!Number.isFinite(ts)) continue
      if (ts < refMs - windowMs || ts > refMs) continue
    }
    inPeriod.push(record)
  }

  let inputTotal = 0
  let outputTotal = 0
  let estimatedCount = 0
  const bySession = new Map()
  const byModel = new Map()
  for (const record of inPeriod) {
    const input = tokenCount(record.input_tokens)
    const output = tokenCount(record.output_tokens)
    inputTotal += input
    outputTotal += output
    if (record.estimated === true) estimatedCount++
    bump(bySession, record.session_id, input, output)
    bump(byModel, record.model, input, output)
  }
  const total = inputTotal + outputTotal

  const out = []
  if (typeof options.threshold === "number" && Number.isFinite(options.threshold) && total > options.threshold) {
    out.push(`WARNING: token budget exceeded for period "${period}": total ${total} > threshold ${options.threshold}`)
  }
  out.push("token-budget report")
  out.push(`period: ${period}`)
  out.push(
    period === "all"
      ? "window: all time"
      // Нет записей и опорное время не задано явно → реальное окно
      // отсутствует; рисуем 1970-epoch только когда это настоящие ts=0.
      : refMs === 0 && options.now == null
        ? "window: n/a (no records)"
        : `window: ${new Date(refMs - windowMs).toISOString()} .. ${new Date(refMs).toISOString()}`,
  )
  out.push(`records: ${inPeriod.length} in period (malformed skipped: ${malformed}, estimated: ${estimatedCount})`)

  if (inPeriod.length === 0) {
    out.push("no records in period")
    return out.join("\n") + "\n"
  }

  out.push(`totals: input=${inputTotal} output=${outputTotal} total=${total}`)
  out.push("")
  out.push("by session:")
  out.push(...renderBreakdown(bySession))
  out.push("")
  out.push("by model:")
  out.push(...renderBreakdown(byModel))
  return out.join("\n") + "\n"
}

function tokenCount(value) {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : 0
}

function bump(map, key, input, output) {
  const name = typeof key === "string" && key.length > 0 ? key : "(unknown)"
  let entry = map.get(name)
  if (entry === undefined) {
    entry = { input: 0, output: 0, records: 0 }
    map.set(name, entry)
  }
  entry.input += input
  entry.output += output
  entry.records++
}

// Таблица разбивки: ключи по возрастанию, колонки выровнены по данным
// (детерминированно при одном и том же входе).
function renderBreakdown(map) {
  const keys = Array.from(map.keys()).sort()
  if (keys.length === 0) return ["  (none)"]
  const rows = keys.map((key) => {
    const entry = map.get(key)
    return {
      name: key,
      input: entry.input,
      output: entry.output,
      total: entry.input + entry.output,
      records: entry.records,
    }
  })
  const width = (values) => Math.max(...values.map((value) => String(value).length))
  const wName = width(rows.map((row) => row.name))
  const wInput = width(rows.map((row) => row.input))
  const wOutput = width(rows.map((row) => row.output))
  const wTotal = width(rows.map((row) => row.total))
  const wRecords = width(rows.map((row) => row.records))
  return rows.map(
    (row) =>
      `  ${row.name.padEnd(wName)}  input=${String(row.input).padStart(wInput)}  output=${String(row.output).padStart(wOutput)}  total=${String(row.total).padStart(wTotal)}  records=${String(row.records).padStart(wRecords)}`,
  )
}

// Auto-discovery loads every module in this directory as a plugin and expects
// its default export to be callable. Keep the helper surface on that function
// so CommonJS require() destructuring still exposes the named helpers.
export default Object.assign(async () => ({}), {
  REDACT_REPLACEMENT,
  REDACT_PATTERNS,
  SECRET_KEY_RE,
  CONTENT_KEY_RE,
  redactString,
  redactFields,
  buildAuditRecord,
  buildTokenRecord,
  estimateTokens,
  appendJsonlRecord,
  readJsonlLines,
  buildReport,
})
