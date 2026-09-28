// ~/.config/opencode/plugins/input-security.ts
// T-137 — санитизация ввода + secret redaction (порт M Code в TUI).
// Нативный V2-формат (OpenCode 2.0.18): Plugin.define({ id, setup(ctx) }).
//
// Маппинг хуков V1 → V2:
//   chat.message → ctx.session.hook("prompt", ...)
//     V1 санитизировал text-части message.parts → V2: санитизация event.prompt.text
//     (у PromptInput.Prompt есть только text/files/agents/skills — подтверждено по схеме)
//   experimental.chat.messages.transform → ctx.session.hook("context", ...)
//     с правкой event.messages: поле V2 — entry.content (не entry.parts),
//     part-формы V2 — text/media/tool-call/tool-result (не V1 tool/state)
//
// Fail-safe: любая ошибка логируется, turn не роняется.

import { Plugin } from "@opencode/plugin"
import { sanitizeText, redactText } from "../lib/input-security-helpers.js"

const redactContent = (content: any[]): void => {
  for (const part of content ?? []) {
    if (!part) continue
    if (part.type === "text" && typeof part.text === "string") {
      part.text = redactText(part.text)
    } else if (part.type === "tool-result" && part.result) {
      const res = part.result
      if ((res.type === "text" || res.type === "error") && typeof res.value === "string") {
        res.value = redactText(res.value)
      } else if (res.type === "content" && Array.isArray(res.value)) {
        redactContent(res.value)
      } else if (res.type === "json" && typeof res.value === "string") {
        res.value = redactText(res.value)
      }
    }
  }
}

export default Plugin.define({
  id: "input-security",
  async setup(ctx) {
    // V1 chat.message → V2 prompt admission hook.
    // Подтверждено по схеме: у PromptInput.Prompt только text/files/agents/skills,
    // parts нет — санитизируется только text (файлы/упоминания резолвятся отдельным
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
    await ctx.session.hook("context", (event: { messages?: Array<{ content?: any[] }> }) => {
      try {
        for (const entry of event?.messages ?? []) {
          redactContent(entry?.content)
        }
      } catch (err) {
        console.error(`[input-security] redact failed: ${err}`)
      }
    })
  },
})
