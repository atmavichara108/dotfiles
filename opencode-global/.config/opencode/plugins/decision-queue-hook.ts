// Decision Queue runtime hook: metadata-only card creation on permission events.
// Нативный V2-формат (OpenCode 2.0.18): Plugin.define({ id, setup(ctx) }).
//
// Маппинг хуков V1 → V2:
//   permission.ask → ctx.permission.hook("evaluate", ...)
//     V1 PermissionEvent { type, pattern, title, sessionID, messageID, callID, metadata }
//     → V2 PermissionEvaluation { action, resources, sessionID, source, metadata, message }
//   event catch-all (fallback) → ctx.event.subscribe(), фильтр event.type
//     V1 permission.ask / permission.request → V2 стрим-событие "permission.asked"
//
// Логика создания карточек (createCard/writeCard, inferRisk, sanitizeReason,
// generateCardId) сохранена 1:1 — меняется только адаптация входного события.

import { Plugin } from "@opencode/plugin"
import { appendFile, mkdir } from "fs/promises"
import { join } from "path"
import { existsSync } from "fs"
import { inferRisk, sanitizeReason, generateCardId } from "../lib/decision-queue-helpers.js"

interface PermissionEvent {
  id?: string
  type?: string
  pattern?: string
  sessionID?: string
  messageID?: string
  callID?: string
  title?: string
  metadata?: Record<string, unknown>
  time?: string
  [key: string]: unknown
}

// V2 ctx.permission.hook("evaluate") — PermissionEvaluation
interface PermissionEvaluateEvent {
  sessionID: string
  agent?: string
  action: string
  resources: readonly string[]
  metadata?: Record<string, unknown>
  source?: { type: string; messageID: string; id: string }
  effect: "allow" | "ask" | "deny"
  message?: string
}

interface DecisionCard {
  id: string
  created: string
  updated: string
  status: "pending" | "approved" | "denied" | "timeout"
  risk: "low" | "medium" | "high" | "critical"
  type: string
  pattern: string
  title: string
  reason: string
  sessionID: string
  messageID: string
  callID: string
  metadata: Record<string, unknown>
}

const VAULT_PATH = "/home/rudra/Projects/OpenCode-Vault/decision-queue"
const FALLBACK_PATH = "/home/rudra/.local/share/opencode/decision-queue"

function getStoragePath(): string {
  return existsSync(VAULT_PATH) ? VAULT_PATH : FALLBACK_PATH
}

function createCard(event: PermissionEvent): DecisionCard {
  const now = new Date().toISOString()
  const type = event.type ?? "unknown"
  const pattern = event.pattern ?? ""
  const risk = inferRisk(type, pattern)

  return {
    id: generateCardId(type, pattern),
    created: now,
    updated: now,
    status: "pending",
    risk: risk as DecisionCard["risk"],
    type,
    pattern,
    title: event.title ?? "Permission request",
    reason: sanitizeReason(event.title ?? "Permission event captured"),
    sessionID: event.sessionID ?? "unknown",
    messageID: event.messageID ?? "unknown",
    callID: event.callID ?? "unknown",
    metadata: event.metadata ?? {},
  }
}

async function writeCard(card: DecisionCard) {
  const storagePath = getStoragePath()
  const cardsDir = join(storagePath, "cards")
  const cardPath = join(cardsDir, `${card.id}.json`)

  try {
    await mkdir(cardsDir, { recursive: true })
    await appendFile(cardPath, JSON.stringify(card, null, 2) + "\n", "utf-8")
    console.log(`[decision-queue-hook] card created: ${card.id} (risk: ${card.risk})`)
  } catch (err) {
    console.error(`[decision-queue-hook] card write failed: ${err}`)
  }
}

// Адаптация V2 PermissionEvaluation → V1-shaped PermissionEvent для createCard:
//   type    ← action (например "bash"/"edit"/"read")
//   pattern ← resources (ресурсы/пути) через пробел
//   title   ← message (причина escalated-запроса)
//   messageID/callID ← source { messageID, id }
function fromEvaluate(event: PermissionEvaluateEvent): PermissionEvent {
  return {
    type: event.action,
    pattern: (event.resources ?? []).join(" "),
    sessionID: event.sessionID,
    messageID: event.source?.messageID,
    callID: event.source?.id,
    title: typeof event.message === "string" ? event.message : undefined,
    metadata: event.metadata,
  }
}

// Адаптация V2 стрим-события permission.asked (PermissionV1.Request payload) → PermissionEvent.
// V2-TODO: V1 catch-all фильтровался по "permission.ask" / "permission.request";
// в V2-стриме событие называется "permission.asked" (поля: permission, patterns[], tool).
function fromAsked(event: Record<string, any>): PermissionEvent {
  return {
    id: event.id,
    type: event.permission,
    pattern: Array.isArray(event.patterns) ? event.patterns.join(" ") : "",
    sessionID: event.sessionID,
    messageID: event.tool?.messageID,
    callID: event.tool?.callID,
    metadata: event.metadata,
  }
}

export default Plugin.define({
  id: "decision-queue-hook",
  async setup(ctx) {
    // Primary: V1 permission.ask → V2 permission evaluate hook.
    // Решение (effect) не меняем — только создаём metadata-only карточку, как в V1.
    await ctx.permission.hook("evaluate", async (event: PermissionEvaluateEvent) => {
      try {
        const card = createCard(fromEvaluate(event))
        await writeCard(card)
      } catch (err) {
        console.error(`[decision-queue-hook] permission evaluate handler failed: ${err}`)
      }
    })

    // Fallback: V1 event catch-all → V2 подписка на публичный стрим событий.
    const controller = new AbortController()
    void (async () => {
      for await (const raw of ctx.event.subscribe({ signal: controller.signal })) {
        const event = raw as unknown as Record<string, any>
        if (event?.type !== "permission.asked") continue
        try {
          const card = createCard(fromAsked(event))
          await writeCard(card)
        } catch (err) {
          console.error(`[decision-queue-hook] event fallback handler failed: ${err}`)
        }
      }
    })()

    return () => controller.abort()
  },
})
