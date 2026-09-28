// ~/.config/opencode/plugins/input-security.ts
// T-137 — санитизация ввода + secret redaction (порт M Code в TUI).
// Нативный V2-формат (OpenCode 2.0.18): Plugin.define({ id, setup(ctx) }).
//
// Маппинг хуков V1 → V2:
//   chat.message → ctx.session.hook("prompt", ...)
//     V1 санитизировал text-части message.parts → V2: санитизация event.prompt.text
//   experimental.chat.messages.transform → ctx.session.hook("context", ...)
//     с правкой event.messages (redactParts по entry.parts — 1:1)
//
// Fail-safe: любая ошибка логируется, turn не роняется.

import { Plugin } from "@opencode/plugin"
import { sanitizeText, redactText } from "../lib/input-security-helpers.js"

const redactParts = (parts: any[]) => {
  for (const part of parts ?? []) {
    if (!part) continue
    if (part.type === "text" && typeof part.text === "string") {
      part.text = redactText(part.text)
    } else if (part.type === "tool" && part.state?.status === "completed" && typeof part.state.output === "string") {
      part.state.output = redactText(part.state.output)
    }
  }
}

export default Plugin.define({
  id: "input-security",
  async setup(ctx) {
    // V1 chat.message → V2 prompt admission hook.
    // V2-TODO: у prompt-hook есть только prompt.text/files/agents/skills — структуры
    // parts нет, санитизируется только text (файлы/упоминания резолвятся отдельным
    // конвейером и V1-санитизации не подвергались).
    await ctx.session.hook("prompt", (event: { prompt: { text?: string } }) => {
      try {
        if (typeof event?.prompt?.text === "string") {
          event.prompt.text = sanitizeText(event.prompt.text)
        }
      } catch (err) {
        console.error(`[input-security] sanitize failed: ${err}`)
      }
    })

    // V1 experimental.chat.messages.transform → V2 context hook (messages уходят модели).
    await ctx.session.hook("context", (event: { messages?: Array<{ parts?: any[] }> }) => {
      try {
        for (const entry of event?.messages ?? []) {
          redactParts(entry?.parts)
        }
      } catch (err) {
        console.error(`[input-security] redact failed: ${err}`)
      }
    })
  },
})
