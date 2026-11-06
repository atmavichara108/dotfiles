// ~/.config/opencode/plugins/secrets-guard.ts
// Гейт путей секретов (мандат СБ C1-остаток, 2026-11-06).
// Смысл: секреты не должны попадать в модель «легально» через bash.
// Легитный доступ владельца — через owner-gate ask_secret (target=~/.secrets).
//
// Fail-closed на подозрении: команда трогает путь ~/.secrets или .secrets/ и
// похожа на чтение/копирование — блокируем. Осознанный обход: `SECRETS_OK=1`.
// Fail-open на ошибках разбора (логируем, turn не роняем).

import { Plugin } from "@opencode/plugin"

const SECRET_PATH_RE = /(^|[\s'"=(~])(\~?\/?\.secrets\/)/i  // secrets-scan:allow (гейт: имя переменной содержит слово secret)
const READ_CMD_RE =
  /(^|;|&&|\|\|)\s*(sudo\s+)?(cat|bat|less|more|head|tail|rg|grep|awk|sed|xxd|strings|cp|mv|ln|tar|zip|unzip|rsync|scp|python3?|openssl|jq|yq|diff|find|findstr)\b[^\n]*\b(^(~?\/?)\.secrets\/|\~\/\.secrets\/|\.secrets\/)/i

export default Plugin.define({
  id: "secrets-guard",
  async setup(ctx) {
    await ctx.tool.hook("execute.before", async (event: { tool?: string; input?: unknown }) => {
      try {
        if (process.env.SECRETS_OK === "1") return
        if (String(event?.tool ?? "").toLowerCase() !== "bash") return
        const cmd = String((event?.input as { command?: unknown })?.command ?? "")
        if (!cmd) return

        // Быстрый фильтр: команда вообще упоминает каталог секретов.
        if (!SECRET_PATH_RE.test(cmd)) return

        // Разрешаем явное упоминание в нерабочем контексте (например, echo пути),
        // но блокируем реальные читающие операции.
        const normalized = cmd.replace(/\s+/g, " ").trim()
        if (READ_CMD_RE.test(normalized)) {
          throw new Error(
            "SecretsGuard: обращение к ~/.secrets/** заблокировано. " +
              "Секреты не читаются моделью; легитный путь — owner-gate ask_secret " +
              "(target=~/.secrets). Осознанный обход: SECRETS_OK=1 с причиной.",
          )
        }
      } catch (err) {
        if (err instanceof Error && err.message.startsWith("SecretsGuard:")) throw err
        console.error(`[secrets-guard] check failed: ${err}`)
      }
    })
  },
})
