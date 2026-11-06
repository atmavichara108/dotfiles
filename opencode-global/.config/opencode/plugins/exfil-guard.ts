// ~/.config/opencode/plugins/exfil-guard.ts
// Гейт рантайма для исходящих данных (мандат СБ, 2026-11-06).
// Не пускает сетевые исходящие команды в обход permission-списка.
//
// Почему: `bash` с вложенным `curl`/`wget`/`ssh`/`scp`/`rsync` внутри пайпа
// не всегда попадает под prefix-permission `curl*`; без гейта это тихая
// утечка данных за пределы хоста. Гейт fail-open на ошибках, но fail-closed
// на подозрении.
//
// Обход (осознанный): `EXFIL_OK=1` в окружении команды.
// Внешние fetch-инструменты OpenCode (webfetch/websearch) покрываются
// обычным permission-контуром и здесь не дублируются.

import { Plugin } from "@opencode/plugin"

export default Plugin.define({
  id: "exfil-guard",
  async setup(ctx) {
    const NET_RE = /\b(curl|wget|ssh|scp|rsync|nc|ncat)\b/
    const NET_PREFIX_RE = /^(curl|wget|ssh|scp|rsync|nc|ncat)\b/

    await ctx.tool.hook("execute.before", async (event: { tool?: string; input?: unknown }) => {
      try {
        if (process.env.EXFIL_OK === "1") return
        if (String(event?.tool ?? "").toLowerCase() !== "bash") return
        const cmd = String((event?.input as { command?: unknown })?.command ?? "")
        if (!cmd) return
        // Если команда начинается с известной сетевой утилиты, её шильдит
        // permission-контур (`curl*`, `wget*`, `ssh*`, ...). Гейт ловит
        // только вложенные/замаскированные случаи.
        if (NET_PREFIX_RE.test(cmd.trim())) return
        if (NET_RE.test(cmd)) {
          throw new Error(
            "ExfilGuard: исходящая сетевая команда обнаружена не напрямую. " +
            "Разрешаю только через permission-контур (curl*/wget*/ssh*/scp*/rsync*) " +
            "или осознанно EXFIL_OK=1.",
          )
        }
      } catch (err) {
        if (err instanceof Error && err.message.startsWith("ExfilGuard:")) throw err
        console.error(`[exfil-guard] check failed: ${err}`)
      }
    })
  },
})
