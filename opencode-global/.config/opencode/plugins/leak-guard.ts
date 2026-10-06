// ~/.config/opencode/plugins/leak-guard.ts
// Secret guard — redact known local secrets from tool outputs / context
// messages before they reach the model. V2-native Plugin.define, pattern
// follows input-security.ts (same context hook, same content walker).
//
// Secret collection (cache with mtime/size invalidation):
//   createSecretsCollector() reads OpenCode storages via helpers
//     ~/.config/opencode/service.json    — поле "password"
//     ~/.local/share/opencode/auth.json  — все строковые значения
//     ~/.local/state/opencode/service.json — поле "password"
//   and filters by SECRET_GUARD_MIN_LENGTH (default 12).
//
// Cache policy:
//   - Snapshot of mtime+size for each source file.
//   - Re-read at most once per 5 seconds (debounce).
//   - If any source file's mtime or size changed since last read,
//     the secret set is rebuilt. This covers password rotation via
//     `opencode service set password ...` without a backend restart.
//   - Read errors are swallowed (fail-safe): the previous cache is
//     retained, no turn is killed.
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
import { createSecretsCollector, redactExact } from "../lib/leak-guard-helpers.js"

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
    // Cache with mtime/size invalidation; rebuilds when source files
    // change (e.g. after password rotation) no more often than once
    // per 5 seconds. Errors stay inside the collector (fail-safe).
    const collector = createSecretsCollector()

    try {
      // V2 context hook — messages, уходящие модели (включая tool-result).
      // Паттерн идентичен input-security.ts.
      await ctx.session.hook("context", (event: { messages?: Array<{ content?: any[] }> }) => {
        try {
          const secrets = collector.getSecrets()
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
