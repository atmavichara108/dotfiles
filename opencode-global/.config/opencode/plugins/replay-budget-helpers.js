// replay-budget-helpers.js
// Pure helper functions for the replay-budget plugin (T-135: порт M Code replay budget в TUI).
// Shared between the plugin and the smoke test. No runtime deps, no side effects
// beyond the in-place mutation passed to applyReplayBudget.
//
// Semantics and constants mirrored 1:1 from M Code Desktop (verified in app.asar,
// 01-Reference/mcode-desktop.md § "Replay budget — главное"):
//   TOOL_OUTPUT_MAX_CHARS = 2000  — старый tool-результат режется (head 75% / tail 25%)
//   REPLAY_PROTECTED_CHARS = 40000 — последние tool-результаты суммарно до 40 KB едут целиком
//   PRUNED_INPUT_MIN_CHARS = 120  — длинные строки старых tool-входов заменяются маркером
//   IMAGE_BUDGET = 5              — из истории держится ≤5 картинок
//   reasoning старых ходов не переигрывается (только текущий assistant-ход)

export const TOOL_OUTPUT_MAX_CHARS = 2000
export const REPLAY_PROTECTED_CHARS = 40000
export const PRUNED_INPUT_MIN_CHARS = 120
export const IMAGE_BUDGET = 5
export const HEAD_RATIO = 0.75

// Поля tool-входов, которые переживают pruning (PRUNED_INPUT_KEEP в M Code).
export const PRUNED_INPUT_KEEP = [
  "filePath",
  "path",
  "command",
  "pattern",
  "description",
  "subagent_type",
  "name",
  "url",
  "offset",
  "limit",
]

const MARKER_PREFIX = "[mcode: replay budget"

/**
 * Обрезка старого tool-результата до maxChars: head 75% + tail 25%,
 * middle-elision с честным маркером, сколько символов упущено.
 * Возвращает исходную строку, если резать нечего.
 */
export function truncateToolOutput(text, maxChars = TOOL_OUTPUT_MAX_CHARS) {
  if (typeof text !== "string" || text.length <= maxChars) return text
  const headChars = Math.floor(maxChars * HEAD_RATIO)
  const tailChars = maxChars - headChars
  const head = text.slice(0, headChars)
  const tail = text.slice(text.length - tailChars)
  const omitted = text.length - headChars - tailChars
  const marker = `${MARKER_PREFIX} — omitted ${omitted} chars (${headChars} head + ${tailChars} tail shown)]`
  return `${head}\n${marker}\n${tail}`
}

/**
 * Pruning старых tool-входов: строковые поля длиннее minChars (кроме keep-полей)
 * заменяются на `[N characters cleared]`. Мутирует объект in-place, ограниченной глубиной
 * (защита от циклов).
 */
export function pruneToolInput(input, minChars = PRUNED_INPUT_MIN_CHARS, keep = PRUNED_INPUT_KEEP, depth = 0) {
  if (input == null || typeof input !== "object" || depth > 3) return input
  const keepSet = keep instanceof Set ? keep : new Set(keep)
  for (const key of Object.keys(input)) {
    const value = input[key]
    if (typeof value === "string") {
      if (value.length > minChars && !keepSet.has(key)) {
        input[key] = `[${value.length} characters cleared]`
      }
    } else if (Array.isArray(value)) {
      for (const item of value) pruneToolInput(item, minChars, keep, depth + 1)
    } else if (typeof value === "object") {
      pruneToolInput(value, minChars, keep, depth + 1)
    }
  }
  return input
}

/**
 * Замена картинки, вышедшей за image budget, на текстовый маркер (in-place,
 * без type-surgery: file-часть превращается в text-часть). Мутирует part.
 */
export function clearImagePart(part, budget = IMAGE_BUDGET) {
  part.type = "text"
  part.text = `[Image omitted: replay budget keeps at most ${budget} images from history]`
  delete part.mime
  delete part.url
  delete part.filename
  delete part.source
  return part
}

/**
 * Оркестратор replay budget. Мутирует messages (массив {info, parts}) in-place —
 * это требование хука experimental.chat.messages.transform: изменения должны попасть
 * в тот же массив, который конвертируется в model messages.
 *
 * Проход с конца (newest→oldest): защитный бюджет тратится на последние tool-результаты.
 */
export function applyReplayBudget(messages, opts = {}) {
  const {
    toolOutputMaxChars = TOOL_OUTPUT_MAX_CHARS,
    protectedChars = REPLAY_PROTECTED_CHARS,
    inputMinChars = PRUNED_INPUT_MIN_CHARS,
    imageBudget = IMAGE_BUDGET,
    keep = PRUNED_INPUT_KEEP,
  } = opts

  if (!Array.isArray(messages)) return messages

  // reasoning текущего assistant-хода сохраняется; старые — дропаются.
  let newestAssistantIndex = -1
  for (let i = messages.length - 1; i >= 0; i--) {
    const info = messages[i] && messages[i].info
    if (info && info.role === "assistant") {
      newestAssistantIndex = i
      break
    }
  }

  let protectedBudget = protectedChars
  let imageCount = 0

  for (let i = messages.length - 1; i >= 0; i--) {
    const entry = messages[i]
    if (!entry || !Array.isArray(entry.parts)) continue

    for (const part of entry.parts) {
      if (!part) continue

      if (part.type === "tool") {
        const state = part.state
        if (!state) continue
        if (state.input != null) pruneToolInput(state.input, inputMinChars, keep)
        if (state.status === "completed" && typeof state.output === "string") {
          if (state.output.length > toolOutputMaxChars && protectedBudget <= 0) {
            state.output = truncateToolOutput(state.output, toolOutputMaxChars)
          } else {
            protectedBudget -= state.output.length
          }
        }
      } else if (part.type === "reasoning") {
        if (i !== newestAssistantIndex) part.text = ""
      } else if (part.type === "file" && typeof part.mime === "string" && part.mime.startsWith("image/")) {
        imageCount++
        if (imageCount > imageBudget) clearImagePart(part, imageBudget)
      }
    }
  }

  return messages
}

export default {
  TOOL_OUTPUT_MAX_CHARS,
  REPLAY_PROTECTED_CHARS,
  PRUNED_INPUT_MIN_CHARS,
  IMAGE_BUDGET,
  PRUNED_INPUT_KEEP,
  truncateToolOutput,
  pruneToolInput,
  clearImagePart,
  applyReplayBudget,
}