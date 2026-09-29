// ~/.config/opencode/plugins/deepseek-tool-discipline.ts
// Дисциплина tool calling для локального моста DeepSeek (local-deepseek).
//
// Зачем: у веб-чата DeepSeek нет нативного function calling — мост
// эмулирует его текстом. Модель склонна «описывать» действие вместо вызова
// (печатает JSON/прозу), и тогда opencode ничего не выполняет. Плагин
// добавляет жёсткую позднюю системную инструкцию только для этого провайдера.
//
// V2 API (проверено по соседнему input-security.ts):
//   Plugin.define({ id, setup(ctx) }) + ctx.session.hook("context", ...)
// В1-версия из репозитория моста (experimental.chat.system.transform)
// на opencode 2.x не грузится: "Plugin must export a default definition
// with an id and an effect or hooks" — формат экспорта изменился.
//
// Fail-open: любая ошибка логируется и не мешает работе.

import { Plugin } from "@opencode/plugin"

const PROVIDER_ID = "local-deepseek"

const INSTRUCTION =
  "CRITICAL (tool discipline, local-deepseek): to ACT you MUST emit real tool calls. " +
  "Never describe the action in prose, never print JSON/XML or a ```tool_calls``` block as " +
  "visible text. Call the tool function itself. If you want to change a file, call the " +
  "write/edit tool now — not in the next turn, and not as a code block."

export default Plugin.define({
  id: "deepseek-tool-discipline",
  async setup(ctx) {
    await ctx.session.hook(
      "context",
      (event: {
        messages?: Array<{ role?: string; content?: any[]; modelID?: string; providerID?: string }>
      }) => {
        try {
          const messages = event?.messages
          if (!Array.isArray(messages) || messages.length === 0) return

          // Целимся только в сообщения, помеченные нашим провайдером.
          const isDeepseek = messages.some(
            (m) => m?.providerID === PROVIDER_ID || m?.modelID?.startsWith(PROVIDER_ID + "/"),
          )
          if (!isDeepseek) return

          const already = messages.some(
            (m) =>
              m?.role === "system" &&
              Array.isArray(m?.content) &&
              m.content.some((part: any) => String(part?.text ?? "").includes("tool discipline, local-deepseek")),
          )
          if (already) return

          messages.push({
            role: "system",
            content: [{ type: "text", text: INSTRUCTION }],
          } as any)
        } catch (err) {
          console.error(`[deepseek-tool-discipline] failed: ${err}`)
        }
      },
    )
  },
})
