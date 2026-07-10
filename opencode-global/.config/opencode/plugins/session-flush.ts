// ~/.config/opencode/plugins/session-flush.ts
// Детерминированный плагин: копит изменённые файлы, при idle дописывает в session-log.
// Агентов НЕ вызывает.

import type { Plugin } from "@opencode-ai/plugin"
import { appendFile, mkdir } from "fs/promises"
import { join } from "path"

const plugin: Plugin = async ({ client, $, directory }) => {
  const editedFiles = new Set<string>()

  return {
    // Копим изменённые файлы
    "file.edited": async ({ path }) => {
      editedFiles.add(path)
      client.app.log({
        body: { service: "session-flush", level: "debug", message: `tracked: ${path}` },
      })
    },

    // При idle — дописываем в session-log и очищаем Set
    "session.idle": async () => {
      if (editedFiles.size === 0) return

      const now = new Date()
      const dateStr = now.toISOString().split("T")[0] // YYYY-MM-DD
      const timeStr = now.toTimeString().split(" ")[0] // HH:MM:SS

      const logDir = join(directory, "04-Memory", "session-log")
      const logPath = join(logDir, `${dateStr}.md`)

      // Формируем секцию
      const fileList = Array.from(editedFiles)
        .map((f) => `- ${f}`)
        .join("\n")
      const section = `\n## ${timeStr} — file.edited flush\n\n${fileList}\n`

      try {
        // Убеждаемся что директория существует
        await mkdir(logDir, { recursive: true })
        await appendFile(logPath, section, "utf-8")

        client.app.log({
          body: {
            service: "session-flush",
            level: "info",
            message: `flushed ${editedFiles.size} files to ${logPath}`,
          },
        })

        // Очищаем Set
        editedFiles.clear()
      } catch (err) {
        // Не роняем сессию — логируем ошибку
        client.app.log({
          body: {
            service: "session-flush",
            level: "error",
            message: `flush failed: ${err}`,
          },
        })
      }
    },
  }
}

export default plugin