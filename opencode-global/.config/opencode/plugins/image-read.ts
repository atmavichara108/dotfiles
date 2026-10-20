// ~/.config/opencode/plugins/image-read.ts
// image-read Stage 2 (апрув владельца 2026-10-17, letter-meta-vision-go):
// нативный тул для ВСЕХ агентов, оборачивающий CLI image-read.py (Stage 1).
// Паттерн: telemetry.ts (V2 канон: Plugin.define + ctx.tool.transform).
//
// Локально: OCR tesseract eng+rus + text layout (эвристики, не ML) +
// redaction секретоподобных токенов. Без сети, без LLM.
// Vision-слой (Stage 4) НЕ вынесен в тул — только по отдельному решению
// владельца (O2) + ADR; CLI на --vision отвечает отказом (rc=2).
//
// Пути (переопределяются env):
//   IMAGE_READ_CLI -> ~/.local/bin/image-read.py (stow-симлинк в dotfiles)
//
// Fail-safe: ошибки setup — console.error, сессия не падает; ошибки execute
// возвращаются как content, без throw. CLI fail-closed (нет файла/языков/
// tesseract — отказ с сообщением, rc!=0).

import { Plugin } from "@opencode/plugin"
import { execFile } from "node:child_process"
import { existsSync } from "node:fs"
import os from "node:os"
import path from "node:path"

const cliPath = (): string =>
  process.env.IMAGE_READ_CLI?.trim() ||
  path.join(os.homedir(), ".local", "bin", "image-read.py")

const TIMEOUT_MS = 300_000
const MAX_BUFFER = 10 * 1024 * 1024

type Args = Record<string, unknown>

const asArgs = (input: unknown): Args =>
  input != null && typeof input === "object" ? (input as Args) : {}

const runCli = (cli: string, args: string[]): Promise<string> =>
  new Promise((resolve, reject) => {
    execFile(
      "python3",
      [cli, ...args],
      { timeout: TIMEOUT_MS, maxBuffer: MAX_BUFFER },
      (err, stdout, stderr) => {
        if (err) {
          // rc!=0 CLI — нормальный fail-closed отказ: сообщаем текст stderr
          const msg = (stderr || err.message || String(err)).trim()
          reject(new Error(msg.slice(0, 2000)))
          return
        }
        resolve(stdout)
      },
    )
  })

export default Plugin.define({
  id: "image-read",
  async setup(ctx) {
    try {
      await ctx.tool.transform((editor) => {
        editor.add({
          name: "image-read",
          description:
            "Локальное распознавание изображения: OCR (tesseract eng+rus) + text layout (блоки/строки/слова с координатами, эвристики — не ML) + redaction секретоподобных токенов (e-mail/ключи/парольные значения -> счётчики, контент не выдаётся). Без сети и LLM (Stage 1-3). Выдать JSON-результат. Vision-слой (Stage 4, внешний провайдер) НЕ поддерживается — только по решению владельца (O2) + ADR. path — путь к PNG/JPEG на этом хосте; mode: text|layout|full (default full); langs: через '+' (default eng+rus); psm: 0..13 (default 3).",
          input: {
            type: "object",
            properties: {
              path: {
                type: "string",
                description: "Путь к файлу-изображению (PNG/JPEG) на этом хосте.",
              },
              mode: {
                type: "string",
                enum: ["text", "layout", "full"],
                description:
                  "text — только текст; layout — только блоки с координатами; full — оба (default).",
              },
              langs: {
                type: "string",
                description: "Языки tesseract через '+', default 'eng+rus'.",
              },
              psm: {
                type: "number",
                description: "tesseract page segmentation mode 0..13, default 3 (auto).",
              },
            },
            required: ["path"],
            additionalProperties: false,
          },
          options: { codemode: false },
          async execute(input, context) {
            try {
              if (context?.signal?.aborted) {
                return { content: "image-read: skipped — request aborted before OCR" }
              }
              const args = asArgs(input)
              const file = typeof args.path === "string" ? args.path.trim() : ""
              if (!file) {
                return { content: 'image-read error: "path" (non-empty string) is required' }
              }
              const mode = ["text", "layout", "full"].includes(String(args.mode))
                ? String(args.mode)
                : "full"
              const langs =
                typeof args.langs === "string" &&
                /^[a-z]{2,8}(\+[a-z]{2,8})*$/i.test(args.langs)
                  ? args.langs
                  : "eng+rus"
              const psm =
                Number.isInteger(args.psm) &&
                (args.psm as number) >= 0 &&
                (args.psm as number) <= 13
                  ? (args.psm as number)
                  : 3
              const cli = cliPath()
              if (!existsSync(cli)) {
                return {
                  content: `image-read error: CLI не найден: ${cli} (Stage 1 не stow'нут? stow пакета scripts)`,
                }
              }
              const out = await runCli(cli, [
                file,
                "--mode",
                mode,
                "--langs",
                langs,
                "--psm",
                String(psm),
                "--json",
              ])
              return { content: out }
            } catch (err) {
              const msg = err instanceof Error ? err.message : String(err)
              return { content: `image-read error: ${msg}` }
            }
          },
        })
      })
    } catch (err) {
      // Fail-safe: плагин не должен ронять сессию.
      console.error(`[image-read] setup failed: ${err}`)
    }
  },
})
