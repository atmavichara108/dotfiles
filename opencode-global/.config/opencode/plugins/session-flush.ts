// ~/.config/opencode/plugins/session-flush.ts
// Детерминированный плагин: копит изменённые файлы, при idle дописывает в session-log.
// Агентов НЕ вызывает.
// Нативный V2-формат (OpenCode 2.0.18): Plugin.define({ id, setup(ctx) }).
//
// Маппинг хуков V1 → V2:
//   file.edited  → ctx.event.subscribe(), фильтр event.type === "file.edited"
//                  (V2 payload: { file }; V1 хук получал { path } — читаем оба поля)
//   session.idle → ctx.event.subscribe(), фильтр event.type === "session.idle"
//                  (отдельного хука session.idle в V2 нет)

import { Plugin } from "@opencode/plugin"
import { appendFile, mkdir, stat } from "fs/promises"
import { join } from "path"

export default Plugin.define({
  id: "session-flush",
  async setup(ctx) {
    const directory = ctx.location.directory
    const editedFiles = new Set<string>()

    const flush = async () => {
      if (editedFiles.size === 0) return

      const now = new Date()
      const dateStr = now.toISOString().split("T")[0]
      const timeStr = now.toTimeString().split(" ")[0]

      const logDir = join(directory, "04-Memory", "session-log")
      const logPath = join(logDir, `${dateStr}.md`)

      // Только туда, где 04-Memory уже есть (волт-модель). В чужих проектах
      // ничего не создаём — иначе плодим мусорные каталоги (см. Memory Contract).
      try {
        await stat(logDir)
      } catch {
        console.log(`[session-flush] skip: no 04-Memory in ${directory}`)
        editedFiles.clear()
        return
      }

      const fileList = Array.from(editedFiles)
        .map((f) => `- ${f}`)
        .join("\n")
      const section = `\n## ${timeStr} — file.edited flush\n\n${fileList}\n`

      try {
        await mkdir(logDir, { recursive: true })
        await appendFile(logPath, section, "utf-8")

        console.log(`[session-flush] flushed ${editedFiles.size} files to ${logPath}`)
        editedFiles.clear()
      } catch (err) {
        console.error(`[session-flush] flush failed: ${err}`)
      }
    }

    const controller = new AbortController()

    void (async () => {
      for await (const raw of ctx.event.subscribe({ signal: controller.signal })) {
        const event = raw as unknown as {
          type?: string
          file?: string
          path?: string
          sessionID?: string
        }
        try {
          if (event.type === "file.edited") {
            const file = event.file ?? event.path
            if (!file) continue
            editedFiles.add(file)
            console.log(`[session-flush] tracked: ${file}`)
            continue
          }
          if (event.type === "session.idle") {
            await flush()
          }
        } catch (err) {
          console.error(`[session-flush] event handling failed: ${err}`)
        }
      }
    })()

    // Очистка: AbortController останавливает подписку на события при выгрузке плагина
    return () => controller.abort()
  },
})
