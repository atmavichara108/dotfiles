// ~/.config/opencode/plugins/noop-guard.ts
// T-136 — no-op turn guard (порт M Code в TUI). Ловит «молчаливый» assistant-turn:
// без вызова тула и <200 output tokens → nudge-продолжение, до 3 повторов подряд.
//
// Инструменты (проверенные контракты 1.18.5):
//   - event hook на "session.idle" — turn закончился (generic event, не named-hook)
//   - client.session.messages({ path: { id }, query: { limit } }) — читаем последний assistant
//   - client.session.promptAsync({ path: { id }, body: { parts: [...] } }) — nudge
//   - client.app.log / client.tui.showToast — оповещение
//
// Ограничение честно: promptAsync создаёт synthetic user-message и разбудит модель —
// contra M Code det: это авто-продолжение чужой сессии. Fail-safe: любой сбой логируется,
// turn не пинается дважды (debounce по sessionID · messageID).

import type { Plugin } from "@opencode-ai/plugin"
import {
  NO_OP_RETRY_LIMIT,
  isNoOpTurn,
  buildNudgeParts,
} from "./noop-guard-helpers.js"

const plugin: Plugin = async ({ client }) => {
  // Счётчик повторов no-op по sessionID; дебаунс по последнему assistant messageID,
  // чтобы один и тот же ход не оживал дважды.
  const retries = new Map<string, number>()
  const seen = new Map<string, string>()

  async function handleIdle(sessionID: string) {
    try {
      const res = await client.session.messages({ path: { id: sessionID } })
      const list = res?.data ?? []
      if (!Array.isArray(list) || list.length === 0) return

      // Последний assistant message (не user).
      let lastAssistant = null
      for (let i = list.length - 1; i >= 0; i--) {
        const entry = list[i]
        if (entry?.info?.role === "assistant") {
          lastAssistant = entry
          break
        }
      }
      if (!lastAssistant) return

      const messageID = lastAssistant.info?.id
      const parts = lastAssistant.parts

      // Нормальный ход — сброс счётчика no-op.
      if (!isNoOpTurn(parts)) {
        retries.delete(sessionID)
        seen.delete(sessionID)
        return
      }

      // No-op: дебаунс по messageID.
      const lastSeen = seen.get(sessionID)
      if (messageID && lastSeen === messageID) return
      if (messageID) seen.set(sessionID, messageID)

      const count = (retries.get(sessionID) ?? 0) + 1
      retries.set(sessionID, count)

      client.app.log({
        body: {
          service: "noop-guard",
          level: "warn",
          message: `no-op turn detected (session=${sessionID}, attempt=${count}/${NO_OP_RETRY_LIMIT})`,
        },
      })

      if (count > NO_OP_RETRY_LIMIT) {
        client.tui.showToast({
          body: {
            title: "No-op guard",
            message: `Turn produced no work (${count} continuations) — stopping auto-nudge.`,
            variant: "warning",
          },
        })
        return
      }

      await client.session.promptAsync({
        path: { id: sessionID },
        body: { parts: buildNudgeParts() },
      })
    } catch (err) {
      client.app.log({
        body: {
          service: "noop-guard",
          level: "error",
          message: `no-op guard failed: ${err}`,
        },
      })
    }
  }

  return {
    event: async (input) => {
      const ev = input?.event
      if (!ev || ev.type !== "session.idle") return
      const sessionID = ev?.properties?.sessionID
      if (!sessionID) return
      await handleIdle(sessionID)
    },
  }
}

export default plugin