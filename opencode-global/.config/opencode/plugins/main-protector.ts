// ~/.config/opencode/plugins/main-protector.ts
// Защита main/master от агентских коммитов и от затирания hot-files.
// Нативный V2-формат (OpenCode 2.0.18): Plugin.define({ id, setup(ctx) }).
//
// Маппинг хуков V1 → V2:
//   tool.execute.before → ctx.tool.hook("execute.before", ...)
//     V1 (input.tool, output.args) → V2 (event.tool, event.input)
//   $ Bun shell-хелпер → node:child_process (execFile git rev-parse)
//   directory → ctx.location.directory; client.app.log → console
//
// Fail-safe: любая ошибка git-разведки логируется и НЕ блокирует (fail-open).
// Исключение: `ALLOW_MAIN=1` в окружении — аварийный обход.

import { Plugin } from "@opencode/plugin"
import { execFile } from "node:child_process"

const PROTECTED_BRANCH_RE = /^(main|master)$/
const COMMIT_RE = /\bgit\s+commit\b/
const HOT_FILES = [
  /(^|\/)TASKS\.md$/,
  /(^|\/)00-INDEX\.md$/,
  /(^|\/)active-context\.md$/,
  /(^|\/)registry\.json$/,
  /(^|\/)AGENTS\.md$/,
]

async function currentBranch(directory: string): Promise<string | null> {
  try {
    const stdout = await new Promise<string>((resolve, reject) => {
      execFile(
        "git",
        ["rev-parse", "--abbrev-ref", "HEAD"],
        { cwd: directory },
        (err, out) => (err ? reject(err) : resolve(out)),
      )
    })
    return stdout.trim() || null
  } catch {
    return null
  }
}

async function isProtected(directory: string): Promise<boolean> {
  if (process.env.ALLOW_MAIN === "1") return false
  const branch = await currentBranch(directory)
  return branch !== null && PROTECTED_BRANCH_RE.test(branch)
}

export default Plugin.define({
  id: "main-protector",
  async setup(ctx) {
    const directory = ctx.location.directory

    await ctx.tool.hook("execute.before", async (event: { tool?: string; input?: unknown }) => {
      try {
        if (!(await isProtected(directory))) return

        const tool = String(event?.tool ?? "").toLowerCase()
        const args = (event?.input ?? {}) as Record<string, unknown>

        // 1. git commit в защищённой ветке (кроме merge)
        if (tool === "bash") {
          const cmd = String(args.command ?? "")
          if (COMMIT_RE.test(cmd) && !/\bmerge\b/.test(cmd)) {
            throw new Error("MainProtector: git commit blocked in protected branch (use merge)")
          }
        }

        // 2. edit/write на hot-files
        if (tool === "edit" || tool === "write") {
          const filePath = String(args.filePath ?? args.file ?? "")
          for (const pattern of HOT_FILES) {
            if (pattern.test(filePath)) {
              throw new Error(`MainProtector: hot-file ${filePath} is read-only in protected branch`)
            }
          }
        }
      } catch (err) {
        if (err instanceof Error && err.message.startsWith("MainProtector:")) {
          throw err
        }
        console.error(`[main-protector] guard check failed: ${err}`)
      }
    })
  },
})
