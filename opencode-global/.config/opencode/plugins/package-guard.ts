// ~/.config/opencode/plugins/package-guard.ts
// Гейт агентных установок пакетов (мандат СБ C3, 2026-11-06).
// Не даёт ставить пакеты, которых нет в allowlist или которые «свежие»
// (первая публикация моложе N дней). Легит — allowlist или явное слово владельца
// через PACKAGE_OK=1. Блокирующий вердикт — fail-closed; ошибка самой проверки —
// fail-open, без ложных блоков.

import { Plugin } from "@opencode/plugin"
import { execFile } from "node:child_process"

const INSTALL_RE =
  /\b(pip[0-9.]*\s+install|npm\s+(i|install|add)|pnpm\s+(install|add)|yarn\s+add)\b/i

function runScript(cmd: string): Promise<{ code: number; stderr: string }> {
  return new Promise((resolve) => {
    execFile(
      "/home/rudra/dotfiles/tools/package-guard/package-guard.py",
      ["check", "--cmd", cmd],
      { timeout: 15000 },
      (err, stdout, stderr) => {
        if (err && "code" in err) {
          resolve({ code: Number(err.code ?? 1), stderr: String(stderr ?? "") })
        } else {
          resolve({ code: 0, stderr: String(stderr ?? "") })
        }
      },
    )
  })
}

export default Plugin.define({
  id: "package-guard",
  async setup(ctx) {
    await ctx.tool.hook("execute.before", async (event: { tool?: string; input?: unknown }) => {
      try {
        if (process.env.PACKAGE_OK === "1") return
        if (String(event?.tool ?? "").toLowerCase() !== "bash") return
        const cmd = String((event?.input as { command?: unknown })?.command ?? "")
        if (!cmd || !INSTALL_RE.test(cmd)) return
        const res = await runScript(cmd)
        if (res.code === 2) {
          throw new Error(
            "PackageGuard: установка пакета заблокирована (нет в allowlist или «свежий»). " +
              res.stderr.trim().slice(0, 500),
          )
        }
      } catch (err) {
        if (err instanceof Error && err.message.startsWith("PackageGuard:")) throw err
        console.error(`[package-guard] check failed: ${err}`)
      }
    })
  },
})
