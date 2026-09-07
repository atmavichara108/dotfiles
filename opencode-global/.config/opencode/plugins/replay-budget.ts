// ~/.config/opencode/plugins/replay-budget.ts
// T-135 — порт M Code replay budget в TUI-стек (первый приоритет P6).
// Хук experimental.chat.messages.transform срабатывает прямо перед отправкой
// истории модели (в главном цикле: toModelMessagesEffect(C, Z)). Здесь апстрим
// не капит tool-выводы, поэтому плагин применяет replay budget на месте.
//
// Fail-safe: любая ошибка логируется и не роняет turn — история уходит как есть.
// Семантика и константы — в ./replay-budget-helpers.js (checked из app.asar M Code).

import type { Plugin } from "@opencode-ai/plugin"
import { applyReplayBudget } from "./replay-budget-helpers.js"

const plugin: Plugin = async ({ client }) => {
  return {
    "experimental.chat.messages.transform": async (_input, output) => {
      try {
        if (!output || !Array.isArray(output.messages)) return
        applyReplayBudget(output.messages)
      } catch (err) {
        client.app.log({
          body: {
            service: "replay-budget",
            level: "error",
            message: `replay budget apply failed: ${err}`,
          },
        })
      }
    },
  }
}

export default plugin