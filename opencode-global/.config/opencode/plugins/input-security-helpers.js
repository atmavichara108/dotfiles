// input-security-helpers.js
// Pure helpers for input sanitization + replay redaction (T-137: порт M Code в TUI).
// Shared between plugin and smoke test, no runtime deps.
//
// M Code semantics (verified app.asar, 01-Reference/mcode-desktop.md):
//   SYSTEM_REMINDER_RE = /<system-reminder>([\s\S]*?)<\/system-reminder>/g
//     — system-reminder блоки из вставленного текста вычленяются, чтобы не
//       подделывались как системные директивы (prompt-injection через markup).
//   TRANSPORT_MARKUP — теги <input>/<output>/<thinking>/<system-reminder>/… из
//       пользовательского текста экранируются (затрудняет markup-инъекцию).
//   redactWith(part, PRUNED_INPUT_KEEP) — секреты вычищаются при replay;
//       pattern-based здесь (secrets.expose не настроен в TUI).

export const SYSTEM_REMINDER_RE = /<system-reminder>([\s\S]*?)<\/system-reminder>/g

// Теги transport-markup, которые из пользовательского текста экранируются
// (замена угловых скобок на HTML-entities — тег перестаёт быть разметкой).
export const TRANSPORT_MARKUP_TAGS = [
  "system-reminder",
  "input",
  "output",
  "thinking",
  "tool",
  "result",
  "content",
  "instructions",
  "context",
]

// Паттерны секретов для pattern-based redaction (без secrets.expose).
// Консервативно: только высокоуверенные формы, чтобы не резать легитимный текст.
export const REDACT_PATTERNS = [
  // API-ключи вида sk-...(длинный хвост), OpenAI/Anthropic/GitHub токены
  /\b(sk-[A-Za-z0-9_-]{16,})\b/g,
  /\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b/g,
  // AWS access key id / secret
  /\b(AKIA[0-9A-Z]{16})\b/g,
  /\b(A3T[A-Z0-9]|AGPA[A-Z0-9]|AROA[A-Z0-9]|AIDA[A-Z0-9]|ASIA[A-Z0-9])[A-Z0-9]{16}\b/g,
  // приватные ключи BEGIN ... END
  /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g,
  // bearer-токены
  /\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{16,}\b/gi,
]

export const REDACT_REPLACEMENT = "[redacted]"

/**
 * Вычленить system-reminder блоки из строки (замена на маркер).
 * Защита: text, содержащий <system-reminder>...</system-reminder>, не сможет
 * подделать системную директиву.
 */
export function stripSystemReminders(text) {
  if (typeof text !== "string") return text
  return text.replace(SYSTEM_REMINDER_RE, "[system-reminder removed]")
}

/**
 * Экранировать transport-markup теги: угловые скобки известных тегов → entities.
 * Тег перестаёт интерпретироваться как разметка. Возвращает новую строку.
 */
export function escapeMarkupTags(text) {
  if (typeof text !== "string") return text
  let out = text
  for (const tag of TRANSPORT_MARKUP_TAGS) {
    const open = new RegExp(`<(/?)${escapeRegex(tag)}\\s*>`, "g")
    out = out.replace(open, (_, slash) => `&lt;${slash}${tag}&gt;`)
  }
  return out
}

function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

/**
 * Полная санитизация пользовательского ввода: strip system-reminder + escape markup.
 */
export function sanitizeText(text) {
  return escapeMarkupTags(stripSystemReminders(text))
}

/**
 * Redact секреты по паттернам (pattern-based; secrets.expose не настроен в TUI).
 * Возвращает новую строку.
 */
export function redactText(text) {
  if (typeof text !== "string") return text
  let out = text
  for (const re of REDACT_PATTERNS) {
    out = out.replace(re, REDACT_REPLACEMENT)
  }
  return out
}

export default {
  SYSTEM_REMINDER_RE,
  TRANSPORT_MARKUP_TAGS,
  REDACT_PATTERNS,
  REDACT_REPLACEMENT,
  stripSystemReminders,
  escapeMarkupTags,
  sanitizeText,
  redactText,
}