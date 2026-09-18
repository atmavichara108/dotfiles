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
  buildNudgeParts,
})
