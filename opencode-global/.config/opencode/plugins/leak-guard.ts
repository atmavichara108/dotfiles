// ~/.config/opencode/plugins/leak-guard.ts
// Secret guard — redact known local secrets from tool outputs / context
// messages before they reach the model. V2-native Plugin.define, pattern
// follows input-security.ts (same context hook, same content walker).
//
// Secret collection (lazy, cached per session):
//   collectKnownSecrets() reads OpenCode storages
//     ~/.config/opencode/service.json    — поле "password"
//     ~/.local/share/opencode/auth.json  — все строковые значения
//     ~/.local/state/opencode/service.json — поле "password"
//   and filters by SECRET_GUARD_MIN_LENGTH (default 12).
//
// Hook:
//   ctx.session.hook("context", ...) — тот же паттерн, что input-security:
//   обходим messages[].content[], redact-им text и tool-result строковые
//   значения. ctx.tool.transform здесь не применим: он регистрирует новые
//   инструменты, а не трансформирует вывод существующих.
//
// Приватность: collected secrets НЕ логируются и не печатаются — ни в
// setup, ни в hook, ни в ошибках. В diagnostic — только длина/количество.
//
// Fail-safe: ошибки setup/hook ловятся и логируются (без самих секретов),
// turn не роняется. Отсутствие стораджей → [] → no-op.

import { Plugin } from "@opencode/plugin"
import { collectKnownSecrets, redactExact } from "../lib/leak-guard-helpers.js"

const redactContent = (content: any[] | undefined, secrets: string[]): void => {
  if (!Array.isArray(content)) return
  for (const part of content) {
    if (!part) continue
    if (part.type === "text" && typeof part.text === "string") {
      part.text = redactExact(part.text, secrets)
    } else if (part.type === "tool-result" && part.result) {
      const res = part.result
      if ((res.type === "text" || res.type === "error") && typeof res.value === "string") {
        res.value = redactExact(res.value, secrets)
      } else if (res.type === "content" && Array.isArray(res.value)) {
        redactContent(res.value, secrets)
      } else if (res.type === "json" && typeof res.value === "string") {
        res.value = redactExact(res.value, secrets)
      }
    }
  }
}

export default Plugin.define({
  id: "leak-guard",
  async setup(ctx) {
    // Lazy + cached: секреты собираются один раз при первом hook-вызове.
    // Это позволяет не читать стораджи при старте плагина, если хук не
    // срабатывает, и кэшировать результат в рамках сессии.
    let cachedSecrets: string[] | null = null
    const getSecrets = (): string[] => {
      if (cachedSecrets !== null) return cachedSecrets
      try {
        cachedSecrets = collectKnownSecrets()
      } catch {
        cachedSecrets = []
      }
      return cachedSecrets
    }

    try {
      // V2 context hook — messages, уходящие модели (включая tool-result).
      // Паттерн идентичен input-security.ts.
      await ctx.session.hook("context", (event: { messages?: Array<{ content?: any[] }> }) => {
        try {
          const secrets = getSecrets()
          if (secrets.length === 0) return
          for (const entry of event?.messages ?? []) {
            redactContent(entry?.content, secrets)
          }
        } catch (err) {
          // Fail-safe: не роняем turn. Не логируем сами секреты.
          console.error(
            `[leak-guard] redact failed: ${err instanceof Error ? err.message : String(err)}`,
          )
        }
      })
    } catch (err) {
      // Fail-safe: плагин не роняет сессию.
      console.error(
        `[leak-guard] setup failed: ${err instanceof Error ? err.message : String(err)}`,
      )
    }
  },
})
