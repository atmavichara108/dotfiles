// ~/.config/opencode/plugins/replay-budget.ts
// T-135 — порт M Code replay budget в TUI-стек (первый приоритет P6).
// Нативный V2-формат (OpenCode 2.0.18): Plugin.define({ id, setup(ctx) }).
//
// Маппинг хуков V1 → V2:
//   experimental.chat.messages.transform → ctx.session.hook("context", ...)
//     с правкой event.messages (массив сообщений, уходит в applyReplayBudget 1:1)
//
// Fail-safe: любая ошибка логируется и не роняет turn — история уходит как есть.

import { Plugin } from "@opencode/plugin"
import { applyReplayBudget } from "../lib/replay-budget-helpers.js"

export default Plugin.define({
  id: "replay-budget",
  async setup(ctx) {
    await ctx.session.hook("context", (event: { messages?: unknown[] }) => {
      try {
        if (!event || !Array.isArray(event.messages)) return
        applyReplayBudget(event.messages)
      } catch (err) {
        console.error(`[replay-budget] replay budget apply failed: ${err}`)
      }
    })
  },
})
