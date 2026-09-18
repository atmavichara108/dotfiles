// ~/.config/opencode/plugins/main-protector.ts
// Защита main/master от агентских коммитов и от затирания hot-files.
// Единый runtime-гейт многопотока (часть B, «не бегать за агентами»):
// работает на уровне tool.execute.before, потому неотвратим для любого
// инструмента (bash-`git commit`, edit/write) — как commit-guard/env-guard.
//
// Что блокирует:
//   1. `git commit` в защищённой ветке (main/master), кроме merge.
//      → агент не может оставить работу кучей в каноне; в main только merge.
//   2. edit/write на hot-files (TASKS.md, 00-INDEX.md, active-context.md,
//      registry.json, AGENTS.md) находясь в защищённой ветке.
//      → общий файл в main нельзя молча перезаписать; правь в task-ветке.
//
// Fail-safe: любая ошибка git-разведки логируется и НЕ блокирует (fail-open),
// чтобы плагин никогда не сломал легитимную работу из-за сбоя обхода дерева.
// Исключение: `ALLOW_MAIN=1` в окружении — аварийный обход для осознанных
// release-действий (как в pre-commit hook).

import type { Plugin } from "@opencode-ai/plugin"

const PROTECTED_BRANCH_RE = /^(main|master)$/
const COMMIT_RE = /\bgit\s+commit\b/
const HOT_FILES = [
  /(^|\/)TASKS\.md$/,
  /(^|\/)00-INDEX\.md$/,
  /(^|\/)active-context\.md$/,
  /(^|\/)registry\.json$/,
  /(^|\/)AGENTS\.md$/,
]

async function currentBranch($: any, directory: string): Promise<string | null> {
  try {
    const res = await $`git rev-parse --abbrev-ref HEAD`
      .cwd(directory)
      .nothrow()
      .quiet()
    const out = (res.stdout?.toString() || "").trim()
    return out || null
  } catch {
    return null
  }
}

async function isMerge($: any, directory: string): Promise<boolean> {
  try {
    const res = await $`git rev-parse -q --verify MERGE_HEAD`
      .cwd(directory)
      .nothrow()
      .quiet()
    return (res.stdout?.toString() || "").trim().length > 0
  } catch {
    return false
  }
}

const plugin: Plugin = async ({ client, $, directory }) => {
  const block = async (msg: string) => {
    await client.app
      .log({ body: { service: "main-protector", level: "warn", message: msg } })
      .catch(() => {})
    throw new Error("MainProtector: " + msg)
  }

  return {
    "tool.execute.before": async (input: any, output: any) => {
      try {
        if (process.env.ALLOW_MAIN === "1") return

        if (input.tool === "bash") {
          const cmd = output?.args?.command || ""
          if (!COMMIT_RE.test(cmd)) return

          const branch = await currentBranch($, directory)
          if (!branch || !PROTECTED_BRANCH_RE.test(branch)) return
          if (await isMerge($, directory)) return

          await block(
            `git commit в защищённой ветке '${branch}' запрещён. Работай в task/<slug>-ветке; в main — только merge (или ALLOW_MAIN=1 для осознанного release).`
          )
        }

        if (input.tool === "edit" || input.tool === "write") {
          const fp =
            output?.args?.filePath || output?.args?.path || output?.args?.file_path || ""
          if (typeof fp !== "string" || !fp) return

          const isHot = HOT_FILES.some((re) => re.test(fp))
          if (!isHot) return

          const branch = await currentBranch($, directory)
          if (!branch || !PROTECTED_BRANCH_RE.test(branch)) return

          await block(
            `edit hot-file '${fp}' в защищённой ветке '${branch}' запрещён. Правь в task-ветке, а в main только через merge; для shared-файлов — через peer_lease.`
          )
        }
      } catch (err) {
        // Не роняем сессию лишним логом, если блок уже брошен — пробрасываем,
        // иначе (неожиданная ошибка разведки) логируем и пропускаем (fail-open).
        if (err instanceof Error && err.message.startsWith("MainProtector:")) {
          throw err
        }
        await client.app
          .log({
            body: {
              service: "main-protector",
              level: "error",
              message: `guard check failed: ${err}`,
            },
          })
          .catch(() => {})
      }
    },
  }
}

export default plugin