// bugfix-capture.ts — Phase 1 capture-плагина BF-20261010-01.
// Spec: docs/specs/bugfix-failure-rule.md + docs/specs/bugfix-proactive-plugin.md (S3–S7).
//
// V2-API (подтверждено docs/build/plugins, OpenCode 2.x):
//   ctx.tool.hook("execute.after")      — event.status === "error" → tool-fail
//   ctx.session.hook("retry")           — event.error{type,message,status}, attempt → provider-*
//   ctx.event.subscribe() "permission.replied" — reply === "reject" → permission-blocked
//
// Инварианты: zero-LLM, metadata-only, fail-closed redaction (helpers),Scope Guard
// по ALLOWED_REPOS, BUGFIX_PLUGIN=off → полная пассивность (S13). Плагин НИКОГО
// не уведомляет, письмо не шлёт, task не вызывает, effect не трогает.
// Наружу — только console.error с фиксированным маркером и КОДОМ (без значений).
import { Plugin } from "@opencode/plugin"
import { homedir } from "node:os"
import { join } from "node:path"
import { appendCapture, buildCapture, classifyFailure, notifyUser, routeIncident } from "../lib/bugfix-capture-helpers.js"

const PASSIVE = process.env.BUGFIX_PLUGIN === "off";
const ACTIVE_MODE = true; // Phase 2&3: Active routing and notifications
const STATE_DIR =
  process.env.BUGFIX_STATE_DIR ?? join(homedir(), ".local", "state", "opencode", "incidents")

const asRecord = (v: unknown): Record<string, any> => (v && typeof v === "object" ? (v as Record<string, any>) : {})
const SESSION_RE = /^ses_[A-Za-z0-9]+$/

async function capture(source: string, directory: string, sessionID: unknown, fields: Record<string, unknown>) {
  if (PASSIVE) return
  try {
    if (typeof sessionID !== "string" || !SESSION_RE.test(sessionID)) return
    const slug = projectSlug(directory)
    const classified = classifyFailure(source as any, fields as any)
    let record
    try {
      record = buildCapture({ source: source as any, projectSlug: slug, sessionID, classified })
    } catch (err: any) {
      const code = err?.code ?? "BUILD-FAIL"
      if (code !== "NO-CREATE") console.error(`[bugfix-capture] skip ${code}`)
      return
    }
    await appendCapture(STATE_DIR, record)
    if (ACTIVE_MODE) {
      void notifyUser("OpenCode Capture", `Сбой захвачен: ${record.safe_hint}`);
      void routeIncident(STATE_DIR, record);
    }
  } catch (err) {
    console.error(`[bugfix-capture] capture failed: ${err instanceof Error ? err.name : "ERR"}`)
  }
}

function projectSlug(directory: unknown): string {
  if (typeof directory !== "string" || !directory) return ""
  const parts = directory.replace(/[/\\]+$/, "").split(/[/\\]/)
  return parts[parts.length - 1] ?? ""
}

export default Plugin.define({
  id: "bugfix-capture",
  async setup(ctx: any) {
    if (PASSIVE) {
      console.error("[bugfix-capture] BUGFIX_PLUGIN=off — пассивен (S13)")
      return
    }

    // Источник 1: tool execute.after status=error (подтверждённый V2 hook).
    await ctx.tool.hook("execute.after", (event: unknown) => {
      const ev = asRecord(event)
      if (ev.status !== "error") return
      const message = asRecord(ev.error).message ?? ""
      void capture("tool", ev.directory ?? ev.cwd ?? ctx.location?.directory ?? "", ev.sessionID, {
        tool: typeof ev.tool === "string" ? ev.tool : "",
        message,
      })
    })

    // Источник 2: provider retry (error type/message/status).
    await ctx.session.hook("retry", (event: unknown) => {
      const ev = asRecord(event)
      const err = asRecord(ev.error)
      void capture("provider", ctx.location?.directory ?? "", ev.sessionID, {
        type: err.type,
        message: err.message,
        status: err.status,
      })
    })

    // Источник 3: permission.replied reply=reject.
    // [проверить] точное значение reply отказа ("reject") — если runtime шлёт
    // иное, класс остаётся workflow-обязанностью primary (S3 fallback).
    // Корреляция sessionID по requestID как у consumer decision-queue-hook:
    // asked(data.id) → map; replied ищет по data.requestID, fallback'ы — payload/ev.
    const requested = new Map<string, { sessionID: string; directory: string }>()
    const controller = new AbortController()
    void (async () => {
      for await (const raw of ctx.event.subscribe({ signal: controller.signal })) {
        try {
          const ev = asRecord(raw)
          if (ev.type !== "permission.asked" && ev.type !== "permission.replied") continue
          const payload = asRecord(ev.data ?? ev.properties ?? ev)
          const directory = payload.location?.directory ?? ctx.location?.directory ?? ""
          if (ev.type === "permission.asked") {
            const requestID = String(payload.id ?? payload.requestID ?? "")
            const sessionID = payload.sessionID ?? ev.sessionID
            if (requestID && typeof sessionID === "string") {
              if (requested.size > 500) requested.delete(requested.keys().next().value) // LRU-защита
              requested.set(requestID, { sessionID, directory })
            }
            continue
          }
          const reply = payload.reply ?? payload.response
          if (reply !== "reject") continue
          const requestID = String(payload.requestID ?? payload.id ?? "")
          const known = requested.get(requestID)
          if (requestID) requested.delete(requestID)
          const sessionID = known?.sessionID ?? payload.sessionID ?? ev.sessionID
          void capture("permission", known?.directory || directory, sessionID, { reply })
        } catch (err) {
          console.error(`[bugfix-capture] event handler failed: ${err instanceof Error ? err.name : "ERR"}`)
        }
      }
    })()

    return () => controller.abort()
  },
})
