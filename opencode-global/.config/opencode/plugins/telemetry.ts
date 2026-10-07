// ~/.config/opencode/plugins/telemetry.ts
// T-124 Telemetry P0 (ECO-002) — аудит-лог действий + учёт токенов.
// Нативный V2-формат: Plugin.define({ id, setup(ctx) }); оба инструмента
// регистрируются через ctx.tool.transform (канон V2, см.
// opencode.ai/v2/docs/build/plugins/migrate-v1, "Migrate custom tools").
// V1-конвенции (.opencode/tools/) нет и не используется.
//
// Инструменты:
//   audit-log    — метаданные действий в append-only JSONL
//   token-budget — учёт токенов + детерминированные отчёты (day/week/all)
//
// Пути (переопределяются env):
//   AUDIT_LOG_PATH    → /home/rudra/Projects/OpenCode-Vault/control-plane/audit-log.jsonl
//   TOKEN_BUDGET_PATH → /home/rudra/Projects/OpenCode-Vault/control-plane/telemetry/token-budget.jsonl
//
// Приватность (T-124 §3): логи содержат ТОЛЬКО метаданные (action, ids,
// duration, счётчики); содержимое промптов/ответов не пишется никогда;
// все строковые поля проходят redaction (sk- / Bearer / api_key / password /
// token=); логи append-only. В конфиги (opencode.json*, ~/.config/opencode/**,
// ~/.local/share/**) инструменты не пишут.
//
// Fail-safe: ошибки setup — console.error, сессия не падает; ошибки execute
// возвращаются как content, без throw.

import { Plugin } from "@opencode/plugin"
import {
  appendJsonlRecord,
  buildAuditRecord,
  buildReport,
  buildTokenRecord,
  readJsonlLines,
} from "../lib/telemetry-helpers.js"

const AUDIT_LOG_DEFAULT = "/home/rudra/Projects/OpenCode-Vault/control-plane/audit-log.jsonl"
const TOKEN_BUDGET_DEFAULT = "/home/rudra/Projects/OpenCode-Vault/control-plane/telemetry/token-budget.jsonl"

const auditLogPath = (): string => process.env.AUDIT_LOG_PATH?.trim() || AUDIT_LOG_DEFAULT
const tokenBudgetPath = (): string => process.env.TOKEN_BUDGET_PATH?.trim() || TOKEN_BUDGET_DEFAULT

type Args = Record<string, unknown>

const asArgs = (input: unknown): Args =>
  input != null && typeof input === "object" ? (input as Args) : {}

export default Plugin.define({
  id: "telemetry",
  async setup(ctx) {
    try {
      await ctx.tool.transform((editor) => {
        // --- audit-log: метаданные действий в append-only JSONL ---
        editor.add({
          name: "audit-log",
          description:
            "Append a metadata-only audit record to the append-only audit log (JSONL). Stores action name, session/task ids, duration and small metadata details only — never prompts, model output or secrets (extra fields are dropped, content-like keys are withheld, secret-like strings are redacted).",
          input: {
            type: "object",
            properties: {
              action: {
                type: "string",
                description: "Short action name, e.g. 'tool:grep' or 'stow:apply'.",
              },
              session_id: { type: "string", description: "OpenCode session id, when known." },
              task_id: { type: "string", description: "Task/issue id, e.g. 'T-124'." },
              duration_ms: { type: "number", description: "Action duration in milliseconds." },
              details: {
                type: "object",
                description:
                  "Metadata-only details (counts, paths, statuses). Never put prompts, model output or secrets here: content-like keys are withheld, secret-like strings are redacted.",
              },
            },
            required: ["action"],
            additionalProperties: false,
          },
          // Явная нормальная доступность инструмента агентам (не CodeMode-only):
          // убирает неоднозначность дефолта на разных хостах.
          options: { codemode: false },
          async execute(input, context) {
            try {
              if (context?.signal?.aborted) {
                return { content: "audit-log: skipped — request aborted before write" }
              }
              const record = buildAuditRecord(asArgs(input))
              if (typeof record.action !== "string" || record.action.length === 0) {
                return { content: 'audit-log error: "action" (non-empty string) is required' }
              }
              const path = auditLogPath()
              appendJsonlRecord(path, record)
              return { content: `audit-log: 1 record appended (action=${record.action}, path=${path})` }
            } catch (err) {
              return { content: `audit-log error: ${err instanceof Error ? err.message : String(err)}` }
            }
          },
        })

        // --- token-budget: учёт токенов + детерминированные отчёты ---
        editor.add({
          name: "token-budget",
          description:
            "Token budget telemetry. op=record: append token usage for a session (explicit input_tokens/output_tokens numbers, or a text estimate at ceil(len/4) marked estimated). op=report: build a deterministic usage report from the token log (period day/week/all, optional session_id filter, optional threshold warning).",
          input: {
            type: "object",
            properties: {
              op: {
                type: "string",
                enum: ["record", "report"],
                description: "Operation: record or report.",
              },
              session_id: {
                type: "string",
                description:
                  "record: session the usage belongs to (required). report: optional filter by session.",
              },
              input_tokens: { type: "number", description: "record: explicit input token count." },
              output_tokens: { type: "number", description: "record: explicit output token count." },
              text: {
                type: "string",
                description:
                  "record: estimate tokens from this text (ceil(len/4), marked estimated). Ignored when explicit token counts are given. The text itself is never stored.",
              },
              model: { type: "string", description: "record: model id, when known." },
              period: {
                type: "string",
                enum: ["day", "week", "all"],
                description: "report: window — last 24h, last 7 days, or all time. Defaults to week.",
              },
              threshold: {
                type: "number",
                description: "report: warn when the period total exceeds this many tokens.",
              },
            },
            required: ["op"],
            additionalProperties: false,
          },
          // Явная нормальная доступность инструмента агентам (не CodeMode-only):
          // убирает неоднозначность дефолта на разных хостах.
          options: { codemode: false },
          async execute(input, context) {
            try {
              const args = asArgs(input)
              if (args.op === "record") {
                if (context?.signal?.aborted) {
                  return { content: "token-budget: skipped — request aborted before write" }
                }
                // Хелпер — нетипизированный .js: deno выводит только начальную
                // форму объекта, поэтому приводим к полной форме записи.
                const record = buildTokenRecord(args) as {
                  ts: string
                  session_id: string
                  model?: string
                  input_tokens: number
                  output_tokens: number
                  estimated: boolean
                }
                const path = tokenBudgetPath()
                appendJsonlRecord(path, record)
                return {
                  content: `token-budget: recorded input=${record.input_tokens} output=${record.output_tokens} estimated=${record.estimated} (path=${path})`,
                }
              }
              if (args.op === "report") {
                const period = typeof args.period === "string" ? args.period : "week"
                if (period !== "day" && period !== "week" && period !== "all") {
                  return { content: `token-budget error: unknown period "${period}" (expected day|week|all)` }
                }
                const report = buildReport(readJsonlLines(tokenBudgetPath()), period, {
                  sessionId: typeof args.session_id === "string" ? args.session_id : undefined,
                  threshold: typeof args.threshold === "number" ? args.threshold : undefined,
                })
                return { content: report }
              }
              return { content: 'token-budget error: "op" must be "record" or "report"' }
            } catch (err) {
              return { content: `token-budget error: ${err instanceof Error ? err.message : String(err)}` }
            }
          },
        })
      })
    } catch (err) {
      // Fail-safe: телеметрия не должна ронять сессию.
      console.error(`[telemetry] setup failed: ${err}`)
    }
  },
})
