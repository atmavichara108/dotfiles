// noop-guard-helpers.js
// Pure helpers for the no-op turn guard (T-136: порт M Code no-op guard в TUI).
// Shared between plugin and smoke test, no runtime deps.
//
// M Code semantics (verified app.asar, 01-Reference/mcode-desktop.md § "No-op turn guard"):
//   NO_OP_OUTPUT_THRESHOLD = 200 — turn, закончившийся без вызова тула и <200 output tokens
//   NO_OP_RETRY_LIMIT     = 3   — max nudge-повторов подряд
// Нудж-текст: «сделай работу или скажи одной фразой, что блокирует».

export const NO_OP_OUTPUT_THRESHOLD = 200
export const NO_OP_RETRY_LIMIT = 3

export const NO_OP_NUDGE =
  "You produced no tool calls and no meaningful output on the previous turn. " +
  "Either do the work now, or state in one sentence what is blocking you."

/**
 * Подсчёт output-tokens в last assistant message (parts).
 * Грубая оценка: 1 token ≈ 4 символа текста (без провайдера — консервативно).
 * Возвращает целое число output tokens.
 */
export function countOutputTokens(parts) {
  if (!Array.isArray(parts)) return 0
  let chars = 0
  for (const p of parts) {
    if (p && p.type === "text" && typeof p.text === "string") chars += p.text.length
  }
  return Math.ceil(chars / 4)
}

/**
 * Была ли tool-деятельность в assistant message (успешный/ошибочный вызов тула)?
 * Pending/running тоже считаются деятельностью.
 */
export function hasToolActivity(parts) {
  if (!Array.isArray(parts)) return false
  return parts.some((p) => p && p.type === "tool")
}

/**
 * Является ли последний assistant message no-op turn.
 * Правила M Code: нет вызова тула И output tokens < порога.
 * Возвращает boolean.
 */
export function isNoOpTurn(parts, threshold = NO_OP_OUTPUT_THRESHOLD) {
  if (hasToolActivity(parts)) return false
  const tokens = countOutputTokens(parts)
  return tokens < threshold
}

/**
 * Был ли assistant-ход прерван пользователем (abort/Esc).
 * Сигнал: AssistantMessage.error.name === "MessageAbortedError". Если ход прерван,
 * это не зависание модели — пинать его нуджем бессмысленно и шумно.
 * Принимает объект info (AssistantMessage), не parts.
 */
export function isAbortedTurn(info) {
  return Boolean(info && info.error && info.error.name === "MessageAbortedError")
}

// Маркеры «агент задал вопрос / ждёт подтверждения» — по тексту последнего
// assistant-хода. Вопрос (знак ? в конце) — самый надёжный сигнал; ниже —
// страховка по явным фразам запроса решения/подтверждения/выбора.
const AWAIT_PHRASE_RE =
  /(подтверди|подтвердите|подтверждение|выбери|выберите|выбрать|уточни|уточните|согласуй|согласова|одобри|жду ответа|жду подтверждения|да или нет|нужно ли|можно ли|нужен доступ|нужны права|confirm|approve|should i|want me to|do you want|ok to|which one|pick one|waiting for)/i

/**
 * Ждёт ли агент ответа пользователя (вопрос/просьба о подтверждении)?
 * Такие ходы — осознанная остановка, а не no-op: нудж не нужен.
 */
export function looksLikeAwaitingUser(parts) {
  if (!Array.isArray(parts)) return false
  const textParts = parts.filter(
    (p) => p && p.type === "text" && typeof p.text === "string",
  )
  if (textParts.length === 0) return false
  const last = textParts[textParts.length - 1].text.trim()
  if (last.endsWith("?")) return true
  const joined = textParts.map((p) => p.text).join(" ").trim()
  return Boolean(joined) && AWAIT_PHRASE_RE.test(joined)
}

/**
 * Построить synthetic user nudge-часть для session.prompt/promptAsync.
 * Возвращает [{ type: "text", text: NO_OP_NUDGE, synthetic: true }] (TextPartInput форма SDK).
 * synthetic: true — чтобы нудж не всплывал как настоящий user-ход.
 */
export function buildNudgeParts() {
  return [{ type: "text", text: NO_OP_NUDGE, synthetic: true }]
}

// Auto-discovery loads every module in this directory as a plugin and expects
// its default export to be callable. Keep the helper surface on that function
// so CommonJS require() destructuring still exposes the named helpers.
export default Object.assign(async () => ({}), {
  NO_OP_OUTPUT_THRESHOLD,
  NO_OP_RETRY_LIMIT,
  NO_OP_NUDGE,
  countOutputTokens,
  hasToolActivity,
  isNoOpTurn,
  isAbortedTurn,
  looksLikeAwaitingUser,
  buildNudgeParts,
})
