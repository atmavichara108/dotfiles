// ~/.config/opencode/plugins/tree-hygiene.ts
// Принуждение к чистому дереву при параллельной работе (правило фазы 4).
// Дополняет main-protector (тот держит main-коммиты и hot-files):
//   tree-hygiene — грязное дерево НЕ переживает смену ветки/контекста.
//
// Что блокирует (tool.execute.before):
//   1. `git switch` / `git checkout <ref>` при грязном worktree → throw:
//      агент обязан закоммитить свой сюжет в task-ветку или уложить в stash
//      ДО переключения. Иначе работы разных потоков слипаются в чужой ветке.
//   2. `git stash push` без `-m` при грязном дереве → throw: stash без
//      сообщения = безымянный мусор, из которого потом не разобрать сюжеты.
//
// Обход (осознанный): TREE_HYGIENE=1 в окружении.
// Fail-safe: ошибка git-разведки → fail-open (как main-protector).
// Формат: V2 (OpenCode 2.0.18). После апгрейда рантайма остальные плагины
// мигрируются в этот же формат (см. main-protector.ts).

import { Plugin } from "@opencode/plugin"
import { execFile } from "node:child_process"

const SWITCH_RE = /\bgit\s+(switch|checkout)\b(?![^\n]*\s--\s)/
const HAS_REF_RE = /\bgit\s+(switch|checkout)\s+(-[a-zA-Z]+\s+)*([a-zA-Z0-9_./-]+)/
const STASH_RE = /\bgit\s+stash\s+push\b/

async function isDirty(directory: string): Promise<boolean> {
  try {
    const stdout = await new Promise<string>((resolve, reject) => {
      execFile(
        "git",
        ["status", "--porcelain"],
        { cwd: directory },
        (err, out) => (err ? reject(err) : resolve(out)),
      )
    })
    return stdout.trim().length > 0
  } catch {
    return false // fail-open
  }
}

export default Plugin.define({
  id: "tree-hygiene",
  async setup(ctx) {
    const directory = ctx.location.directory

    await ctx.tool.hook("execute.before", async (event: { tool?: string; input?: unknown }) => {
      try {
        if (process.env.TREE_HYGIENE === "1") return
        if (event?.tool !== "bash") return

        const cmd = String((event.input as Record<string, unknown>)?.command ?? "")

        if (STASH_RE.test(cmd) && !/-m(\s|=)/.test(cmd) && !/--message/.test(cmd)) {
          throw new Error(
            "TreeHygiene: git stash push требует -m <сообщение> — безымянный stash невозможно разобрать при параллельной работе",
          )
        }

        if (SWITCH_RE.test(cmd) && HAS_REF_RE.test(cmd)) {
          if (await isDirty(directory)) {
            throw new Error(
              "TreeHygiene: грязное дерево — закоммить свой сюжет в task-ветку или уложи в именованный stash ДО смены ветки (TREE_HYGIENE=1 для осознанного обхода)",
            )
          }
        }
      } catch (err) {
        if (err instanceof Error && err.message.startsWith("TreeHygiene:")) {
          throw err
        }
        console.error(`[tree-hygiene] guard check failed: ${err}`)
      }
    })
  },
})
