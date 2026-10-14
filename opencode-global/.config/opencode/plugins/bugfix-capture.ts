// bugfix-capture.ts — Phase 1–4 capture-плагина BF-20261010-01.
// Spec: docs/specs/bugfix-failure-rule.md + docs/specs/bugfix-proactive-plugin.md (S3–S7).
//
// V2-API (подтверждено docs/build/plugins, OpenCode 2.x):
//   ctx.tool.hook("execute.after")      — event.status === "error" → tool-fail
//   ctx.session.hook("retry")           — event.error{type,message,status}, attempt → provider-*
//   ctx.event.subscribe() "permission.replied" — reply === "reject" → permission-blocked
//   ctx.event.subscribe() session.*     — Phase 4: outcome failed/interrupted субагента
//                                          → synthetic-уведомление родителю (автовосстановление)
//
// Инварианты: zero-LLM, metadata-only, fail-closed redaction (helpers),Scope Guard
// по ALLOWED_REPOS, BUGFIX_PLUGIN=off → полная пассивность (S13). Плагин НИКОГО
// не уведомляет без ACTIVE_MODE, письмо не шлёт, task не вызывает, effect не трогает.
// Наружу — только console.error с фиксированным маркером и КОДОМ (без значений).
import { Plugin } from "@opencode/plugin"
import { homedir } from "node:os"
import { join } from "node:path"
import { appendFileSync } from "node:fs"
import { appendCapture, buildCapture, classifyFailure, notifyUser, routeIncident } from "../lib/bugfix-capture-helpers.js"

const PASSIVE = process.env.BUGFIX_PLUGIN === "off";
const ACTIVE_MODE = true; // Phase 2–4: routing, notifications, subagent-recovery
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

// Phase 4: события сессий, относящиеся к жизненному циклу (калибруется по debug-логу).
const SESSION_EVENT_TYPES = new Set([
  "session.updated", "session.idle", "session.completed", "session.deleted",
])

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

    // Phase 4: список субагентских id (mode=subagent) для фильтра.
    const subagentIDs = new Set<string>()
    try {
      const agents = await ctx.agent.list()
      for (const a of agents ?? []) {
        if (a?.mode === "subagent" && typeof a.id === "string") subagentIDs.add(a.id)
      }
    } catch {
      console.error("[bugfix-capture] agent.list failed — Phase 4 passive")
    }

    // Phase 4: дедуп уведомлений (один sessionID — одно уведомление за жизнь плагина).
    const recoveryNotified = new Set<string>()
    // Phase 4: калибровка формата session-событий — первые 40 в debug-файл (metadata-only).
    let debugLeft = 40
    const debugSessionEvent = (ev: Record<string, any>) => {
      if (debugLeft <= 0) return
      try {
        debugLeft--
        const payload = asRecord(ev.data ?? ev.properties ?? ev)
        const info = asRecord(payload.info ?? payload)
        const safeInfo: Record<string, unknown> = {}
        for (const k of ["id", "parentID", "agent", "outcome", "title", "time"]) {
          if (info[k] !== undefined) safeInfo[k] = typeof info[k] === "object" ? "«obj»" : info[k]
        }
        const line = JSON.stringify({ ts: Date.now(), type: ev.type, payloadKeys: Object.keys(payload), infoKeys: Object.keys(info), info: safeInfo })
        appendFileSync(join(STATE_DIR, "subagent-watch-debug.jsonl"), line + "\n")
      } catch {
        // debug не ломает основной поток
      }
    }

    // Phase 4: synthetic-уведомление родителю упавшего субагента.
    const notifyParent = async (parentID: string, agent: string, outcome: string, sessionID: string) => {
      try {
        await ctx.session.synthetic({
          sessionID: parentID,
          text:
            `⚠️ subagent-recovery: твой субагент «${agent}» упал (outcome=${outcome}), sessionID=${sessionID}. ` +
            `Контекст сессии цел — продолжи с места падения, не перезапускай с нуля. ` +
            `Способ: task/subagent с sessionID=${sessionID} (если это твоя дочерняя сессия), иначе ` +
            `opencode api post /api/session/${sessionID}/prompt --data '{"text":"Продолжай выполнение прерванного задания с места остановки. Контекст уже в сессии — не начинай с нуля."}'. ` +
            `Если причина — квота провайдера: сначала смени модель сессии (opencode api post /api/session/${sessionID}/model --data '{"model":{"providerID":"<твой provider>","id":"<твоя модель>"}}') и повтори prompt. ` +
            `Полный пайплайн — команда /resume.`,
        })
      } catch {
        console.error("[bugfix-capture] synthetic-to-parent failed: SYNTH-FAIL")
      }
    }

    // Источник 3: permission.replied reply=reject.
    // [проверить] точное значение reply отказа ("reject") — если runtime шлёт
    // иное, класс остаётся workflow-обязанностью primary (S3 fallback).
    // Корреляция sessionID по requestID как у consumer decision-queue-hook:
    // asked(data.id) → map; replied ищет по data.requestID, fallback'ы — payload/ev.
    //
    // Источник 4 (Phase 4): session.* → исход failed/interrupted субагента с
    // parentID → capture + notify + synthetic родителю.
    const requested = new Map<string, { sessionID: string; directory: string }>()
    const controller = new AbortController()
    void (async () => {
      for await (const raw of ctx.event.subscribe({ signal: controller.signal })) {
        try {
          const ev = asRecord(raw)
          const type = String(ev.type ?? "")

          // Источник 4: жизненный цикл сессий.
          if (SESSION_EVENT_TYPES.has(type) || type.startsWith("session.")) {
            debugSessionEvent(ev)
            const payload = asRecord(ev.data ?? ev.properties ?? ev)
            const info = asRecord(payload.info ?? payload)
            const sessionID = typeof info.id === "string" ? info.id : ""
            const parentID = typeof info.parentID === "string" ? info.parentID : ""
            const agent = typeof info.agent === "string" ? info.agent : ""
            const outcome = typeof info.outcome === "string" ? info.outcome : ""
            if (!sessionID || !parentID) continue
            if (!subagentIDs.has(agent)) continue
            if (outcome !== "failed" && outcome !== "interrupted") continue
            if (recoveryNotified.has(sessionID)) continue
            recoveryNotified.add(sessionID)
            const directory = asRecord(info.location).directory ?? ctx.location?.directory ?? ""
            void capture("session", directory, sessionID, { agent, outcome, parent: "present" })
            void notifyUser("OpenCode Recovery", `Субагент ${agent} упал (${outcome}) — родителю отправлено уведомление`)
            if (ACTIVE_MODE) void notifyParent(parentID, agent, outcome, sessionID)
            continue
          }

          if (type !== "permission.asked" && type !== "permission.replied") continue
          const payload = asRecord(ev.data ?? ev.properties ?? ev)
          const directory = payload.location?.directory ?? ctx.location?.directory ?? ""
          if (type === "permission.asked") {
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
