// ~/.config/opencode/plugins/input-security.ts
// T-137 — санитизация ввода + secret redaction (порт M Code в TUI).
// Две точки инъекции (проверены в бинаре 1.18.5):
//   - "chat.message" — новый user-ввод: санитизируем text-части
//     (system-reminder вычленяется, transport-markup экранируется).
//   - "experimental.chat.messages.transform" — replay: redaction секретов
//     в tool-выводах/тексте истории до отправки модели.
//
// Fail-safe: любая ошибка логируется, turn не роняется (история уходит как есть).

import type { Plugin } from "@opencode-ai/plugin"
import { sanitizeText, redactText } from "./input-security-helpers.js"

const plugin: Plugin = async ({ client }) => {
  const sanitizeParts = (parts: any[]) => {
    for (const part of parts ?? []) {
      if (part && part.type === "text" && typeof part.text === "string") {
        part.text = sanitizeText(part.text)
      }
    }
  }

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

  return {
    "chat.message": async (_input, output) => {
      try {
        // SDK: output = { message: UserMessage, parts: Part[] } — санитизируем parts.
        sanitizeParts(output?.parts)
      } catch (err) {
        client.app.log({
          body: { service: "input-security", level: "error", message: `sanitize failed: ${err}` },
        })
      }
    },
    "experimental.chat.messages.transform": async (_input, output) => {
      try {
        for (const entry of output?.messages ?? []) {
          redactParts(entry?.parts)
        }
      } catch (err) {
        client.app.log({
          body: { service: "input-security", level: "error", message: `redact failed: ${err}` },
        })
      }
    },
  }
}

export default plugin