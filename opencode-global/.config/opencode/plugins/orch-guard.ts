// orch-guard — теневой ledger диспетчерских вызовов (metadata-only).
// Нативный V2-формат (OpenCode 2.0.18): Plugin.define({ id, setup(ctx) }).
//
// Назначение: вести учёт вызовов `task` (диспетчеризация субагентов) даже если
// primary забудет CLI-ledger. Дублирующий, пассивный учёт — не гейт, не блок.
//
// Теневой режим — конвенция (как decision-queue-hook.ts, ADR-022):
//   - плагин НИКОГДА не возвращает изменений effect, не вызывает reply,
//     не блокирует и не мутирует событие;
//   - обработчик evaluate всегда завершается без return (undefined);
//   - ошибка записи ledger — только console.error, без проброса;
//   - записи строго metadata-only: ts, sessionID, agent, action, effect,
//     resourceCount. БЕЗ промптов, выводов, путей, секретов.
//
// Охват:
//   - action === "task" — диспетчерский вызов (основной учёт);
//   - action === "edit" — referee-метка (справочно, кто правил файлы вне task).
// Остальные action молча пропускаются.

import { Plugin } from "@opencode/plugin"
import { appendFile, mkdir } from "fs/promises"
import { join } from "path"
import { homedir } from "os"

// V2 ctx.permission.hook("evaluate") — PermissionEvaluation
// (форма повторяет decision-queue-hook.ts).
interface PermissionEvaluateEvent {
  sessionID: string
  agent?: string
  action: string
  resources?: readonly string[]
  metadata?: Record<string, unknown>
  source?: { type: string; messageID: string; id: string }
  effect: "allow" | "ask" | "deny"
  message?: string
}

interface OrchLedgerRecord {
  ts: string
  sessionID: string
  agent: string
  action: string
  kind: "dispatch" | "referee"
  effect: "allow" | "ask" | "deny"
  resourceCount: number
}

function ledgerPath(): string {
  return join(homedir(), ".local", "state", "opencode", "orch-guard", "plugin-ledger.jsonl")
}

function ledgerDir(path: string): string {
  return path.slice(0, path.lastIndexOf("/"))
}

async function appendRecord(record: OrchLedgerRecord): Promise<void> {
  const path = ledgerPath()
  try {
    await mkdir(ledgerDir(path), { recursive: true })
    await appendFile(path, JSON.stringify(record) + "\n", "utf-8")
  } catch (err) {
    // Теневой режим: ошибка записи — только лог, не проброс.
    console.error(`[orch-guard] ledger append failed: ${err}`)
  }
}

export default Plugin.define({
  id: "orch-guard",
  async setup(ctx) {
    await ctx.permission.hook("evaluate", async (event: PermissionEvaluateEvent) => {
      try {
        const action = typeof event.action === "string" ? event.action : ""
        if (action !== "task" && action !== "edit") return

        const record: OrchLedgerRecord = {
          ts: new Date().toISOString(),
          sessionID: typeof event.sessionID === "string" ? event.sessionID : "unknown",
          agent: typeof event.agent === "string" && event.agent ? event.agent : "unknown",
          action,
          kind: action === "task" ? "dispatch" : "referee",
          effect: event.effect,
          resourceCount: Array.isArray(event.resources) ? event.resources.length : 0,
        }
        await appendRecord(record)
      } catch (err) {
        console.error(`[orch-guard] permission evaluate handler failed: ${err}`)
      }
      // ВАЖНО: намеренно без return — effect не мутируется (теневой режим).
    })
  },
})
