// ~/.config/opencode/plugins/session-restart-nudge.ts
// Напоминание о рестарте сессии после правок конфигов, загружаемых при старте.
// Проблема: config/commands/agents не hot-reload — правки вступают в силу
// только после рестарта сессии/TUI, агент забывает сказать об этом.
//
// Механизм (только доказанные V2-примитивы из соседних плагинов):
//   file.edited → ctx.event.subscribe() (как session-flush.ts)
//   prompt hook → ctx.session.hook("prompt") (как input-security.ts)
// Состояние — in-memory Set: рестарт сессии сбрасывает его естественным
// образом, напоминание живёт ровно до рестарта. Ничего не пишет в git.
// Fail-open: любая ошибка логируется и не мешает работе.
//
// Ограничение: правки через shell-редиректы (>> heredoc) отлавливаются
// эвристикой по путям в команде; надёжный путь — edit/write-инструменты.

import { Plugin } from "@opencode/plugin"

// Конфиги, загружаемые при старте сессии/TUI.
const CONFIG_PATTERNS = [
  /(^|\/)opencode\.jsonc?$/,
  /(^|\/)\.opencode\/agent\/[^/]+\.md$/,
  /(^|\/)\.opencode\/command\/[^/]+\.md$/,
  /(^|\/)\.config\/opencode\/agent\/[^/]+\.md$/,
  /(^|\/)\.config\/opencode\/command\/[^/]+\.md$/,
  /(^|\/)\.config\/opencode\/plugins\/[^/]+\.(ts|js)$/,
  /(^|\/)\.config\/opencode\/opencode\.jsonc?$/,
  /(^|\/)\.zshrc$/,
]

// Грубая эвристика для shell-правок (>> heredoc и т.п.).
const SHELL_RE = />>?\s*\S*(opencode\.jsonc?|\.opencode\/(agent|command)\/|opencode\/(agent|command|plugins)\/|\.zshrc)/

function shortLabel(file: string): string {
  const parts = file.split("/")
  return parts.length > 3 ? ".../" + parts.slice(-3).join("/") : file
}

export default Plugin.define({
  id: "session-restart-nudge",
  async setup(ctx) {
    const pending = new Set<string>()
    const controller = new AbortController()

    const track = (file: string | undefined | null) => {
      if (!file) return
      if (CONFIG_PATTERNS.some((re) => re.test(file))) {
        pending.add(shortLabel(file))
        console.log(`[session-restart-nudge] tracked: ${file}`)
      }
    }

    // 1. Синхронный перехват edit/write/apply_patch (как main-protector.ts).
    await ctx.tool.hook("execute.before", async (event: { tool?: string; input?: unknown }) => {
      try {
        const tool = String(event?.tool ?? "").toLowerCase()
        const args = (event?.input ?? {}) as Record<string, unknown>
        if (tool === "edit" || tool === "write" || tool === "apply_patch") {
          const filePath = String(args.filePath ?? args.file ?? args.path ?? "")
          track(filePath)
          return
        }
        if (tool === "bash") {
          const cmd = String(args.command ?? "")
          if (SHELL_RE.test(cmd)) {
            pending.add("shell-правка конфига")
            console.log(`[session-restart-nudge] tracked shell edit`)
          }
        }
      } catch (err) {
        console.error(`[session-restart-nudge] guard failed: ${err}`)
      }
    })

    // 2. Страховка: file.edited из event-стрима (как session-flush.ts).
    void (async () => {
      for await (const raw of ctx.event.subscribe({ signal: controller.signal })) {
        const event = raw as unknown as { type?: string; file?: string; path?: string }
        try {
          if (event?.type !== "file.edited") continue
          track(event.file ?? event.path)
        } catch (err) {
          console.error(`[session-restart-nudge] event failed: ${err}`)
        }
      }
    })()

    // 3. Напоминание в каждый следующий промпт, пока висит pending.
    await ctx.session.hook("prompt", (event: { prompt: { text?: string } }) => {
      try {
        if (pending.size === 0) return
        if (typeof event?.prompt?.text !== "string") return
        const files = Array.from(pending).join(", ")
        event.prompt.text +=
          `\n\n[system-reminder: конфиги сессии менялись (${files}) — ` +
          `вступят в силу после рестарта сессии/TUI. Заверши текущий кусок и перезапустись.]`
      } catch (err) {
        console.error(`[session-restart-nudge] prompt hook failed: ${err}`)
      }
    })

    return () => controller.abort()
  },
})
