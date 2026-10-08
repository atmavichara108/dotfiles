// Decision Queue runtime hook (теневой режим, ADR-022): metadata-only cards on permission events.
// Нативный V2-формат (OpenCode 2.0.18): Plugin.define({ id, setup(ctx) }).
//
// Теневой режим — конвенция, не обход:
//   - плагин НИКОГДА не вызывает reply и не возвращает изменений effect;
//   - конфиг-deny неуязвим («never override a configured deny») — документировано в ADR-022;
//   - детерминированный zero-LLM classify добавляет recommendation{class, rationale,
//     proposed_glob}; сомнение → substantive (только человек).
//
// Маппинг хуков V1 → V2:
//   permission.ask → ctx.permission.hook("evaluate", ...)
//     V1 PermissionEvent { type, pattern, title, sessionID, messageID, callID, metadata }
//     → V2 PermissionEvaluation { action, resources, sessionID, source, metadata, message, effect }
//   event catch-all (fallback) → ctx.event.subscribe(), фильтр event.type
//     V1 permission.ask / permission.request → V2 стрим-событие "permission.asked"
//     + "permission.replied" — дозапись решения человека строго по requestID.
//
// Карточки: <VAULT_PATH>/cards/<requestID>.json — durable-запись (ephemeral
// состояние плагина не является доказательством; своя durable-запись обязательна).

import { Plugin } from "@opencode/plugin"
import { appendFile, mkdir, readFile } from "fs/promises"
import { join } from "path"
import { existsSync } from "fs"
import {
  inferRisk,
  sanitizeReason,
  generateCardId,
  classify,
  parseLastJson,
  mergeDecisionIntoCard,
} from "../lib/decision-queue-helpers.js"

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

interface Recommendation {
  class: "nomenclatural" | "substantive"
  rationale: string
  proposed_glob: string | null
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
  // Теневой классификатор (ADR-022):
  recommendation: Recommendation
  effect: "allow" | "ask" | "deny" | null
  source_directory: string | null
  // agent известен только из evaluate-хука; из стрима asked не добирается.
  source_agent: string | null
  // Плейсхолдер: модель не добирается (требует лишнего API) — см. ADR-022 UNVERIFIED.
  model: string | null
}

const VAULT_PATH = "/home/rudra/Projects/OpenCode-Vault/control-plane/decision-queue"
const FALLBACK_PATH = "/home/rudra/.local/share/opencode/decision-queue"

function getStoragePath(): string {
  return existsSync(VAULT_PATH) ? VAULT_PATH : FALLBACK_PATH
}

function cardsDir(): string {
  return join(getStoragePath(), "cards")
}

function cardPath(id: string): string {
  return join(cardsDir(), `${id}.json`)
}

// requestID — ключ карточки: из permission.asked data.id; при его отсутствии
// (fallback-путь, evaluate-первичная запись) — старый генератор id.
function cardIdFrom(ev: PermissionEvent): string {
  return ev.id && typeof ev.id === "string" ? ev.id : generateCardId(ev.type, ev.pattern)
}

// effect/agent/source_directory известны только из evaluate-хука (null иначе).
function createCard(ev: PermissionEvent, extra?: Partial<DecisionCard> & { metadata_save?: string[] }): DecisionCard {
  const now = new Date().toISOString()
  const type = ev.type ?? "unknown"
  const pattern = ev.pattern ?? ""
  const risk = inferRisk(type, pattern)
  // save[] (предлагаемые глобы «запомнить») приходят из permission.asked;
  // resources — из evaluate. proposed_glob = save[0] || null (ADR-022).
  const resources = pattern ? pattern.split(/\s+/).filter(Boolean) : []
  const recommendation = classify(type, resources, extra?.metadata_save ?? [])

  const card: DecisionCard = {
    id: cardIdFrom(ev),
    created: now,
    updated: now,
    status: "pending",
    risk: risk as DecisionCard["risk"],
    type,
    pattern,
    title: ev.title ?? "Permission request",
    reason: sanitizeReason(ev.title ?? "Permission event captured"),
    sessionID: ev.sessionID ?? "unknown",
    messageID: ev.messageID ?? "unknown",
    callID: ev.callID ?? "unknown",
    metadata: ev.metadata ?? {},
    recommendation: {
      class: recommendation.class,
      rationale: recommendation.rationale,
      proposed_glob: recommendation.proposed_glob,
    },
    effect: null,
    source_directory: null,
    source_agent: null,
    model: null,
  }
  if (extra) Object.assign(card, extra)
  delete (card as Record<string, unknown>).metadata_save
  return card
}

async function writeCard(card: DecisionCard) {
  const dir = cardsDir()
  const path = cardPath(card.id)

  try {
    await mkdir(dir, { recursive: true })
    await appendFile(path, JSON.stringify(card, null, 2) + "\n", "utf-8")
    console.log(
      `[decision-queue-hook] card ${card.id} (risk: ${card.risk}, class: ${card.recommendation.class})`,
    )
  } catch (err) {
    console.error(`[decision-queue-hook] card write failed: ${err}`)
  }
}

// Дозапись решения человека: читаем последнюю запись карточки, мержим, дописываем.
// Match строго по requestID (= id карточки): reject отклоняет все pending-сессии
// ядром, поэтому чужие карточки не должны получать неверный статус.
// Файл карточки может быть pretty-JSON (одна запись) или JSONL-историей (append).
async function appendDecisionToCard(requestID: string, decision: string): Promise<boolean> {
  const path = cardPath(requestID)
  try {
    const raw = await readFile(path, "utf-8")
    const last = parseLastJson(raw)
    const merged = mergeDecisionIntoCard(last, requestID, decision, new Date().toISOString())
    if (!merged) return false
    await appendFile(path, JSON.stringify(merged, null, 2) + "\n", "utf-8")
    console.log(`[decision-queue-hook] card ${requestID} decision recorded: ${decision}`)
    return true
  } catch {
    // карточки с таким requestID нет — чужое/ранее событие, молча пропускаем
    return false
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

// Адаптация V2 стрим-события permission.asked → PermissionEvent.
// Форма: { id, type: "permission.asked", data/properties: { sessionID, permission/action,
// patterns/resources[], save[]?, location?, metadata?, source/tool } }. Читаем data →
// properties → flat (fail-safe: неизвестные поля дают "unknown", карточка всё равно пишется).
function fromAsked(event: Record<string, any>): PermissionEvent {
  const payload = (event?.data ?? event?.properties ?? event ?? {}) as Record<string, any>
  return {
    id: event.id ?? payload.id,
    type: payload.permission ?? payload.action,
    pattern: Array.isArray(payload.resources)
      ? payload.resources.join(" ")
      : Array.isArray(payload.patterns)
        ? payload.patterns.join(" ")
        : Array.isArray(payload.save)
          ? payload.save.join(" ")
          : "",
    sessionID: payload.sessionID,
    messageID: payload.source?.messageID ?? payload.tool?.messageID,
    callID: payload.source?.id ?? payload.tool?.callID,
    title: typeof payload.message === "string" ? payload.message : undefined,
    metadata: payload.metadata,
  }
}

// Дополнительные поля карточки из permission.asked: save[], location.directory.
function extrasFromAsked(event: Record<string, any>): Partial<DecisionCard> & { metadata_save?: string[] } {
  const payload = (event?.data ?? event?.properties ?? event ?? {}) as Record<string, any>
  return {
    metadata_save: Array.isArray(payload.save) ? payload.save.filter((s: unknown) => typeof s === "string") : [],
    source_directory: typeof payload.location?.directory === "string" ? payload.location.directory : null,
  }
}

export default Plugin.define({
  id: "decision-queue-hook",
  async setup(ctx) {
    // Теневое состояние (только чтение): evaluate даёт effect/agent раньше либо
    // параллельно со стримом; храним кратко, только для обогащения карточки.
    // Никаких reply-вызовов, никаких мутаций effect — обработчик возвращает undefined
    // (конвенция теневого режима, ADR-022).
    const pendingByCall = new Map<string, { effect: DecisionCard["effect"]; agent?: string }>()

    // Primary: V1 permission.ask → V2 permission evaluate hook. Только читаем.
    await ctx.permission.hook("evaluate", async (event: PermissionEvaluateEvent) => {
      try {
        if (event.source?.id) {
          pendingByCall.set(event.source.id, { effect: event.effect, agent: event.agent })
        }
        const extra = { effect: event.effect ?? null, source_agent: event.agent ?? null } as Partial<DecisionCard>
        const card = createCard(fromEvaluate(event), extra)
        // evaluate-событие не несёт requestID → id через генератор;
        // обогащение из asked (save/directory) подтянется при его приходе.
        await writeCard(card)
      } catch (err) {
        console.error(`[decision-queue-hook] permission evaluate handler failed: ${err}`)
      }
      // ВАЖНО: намеренно без return — effect не мутируется (теневой режим).
    })

    // Стрим событий: asked → карточка с requestID/save/directory;
    // replied → дозапись решения строго по requestID.
    const controller = new AbortController()
    void (async () => {
      for await (const raw of ctx.event.subscribe({ signal: controller.signal })) {
        const event = raw as unknown as Record<string, any>
        const type = event?.type

        if (type === "permission.asked") {
          try {
            const ev = fromAsked(event)
            const extras = extrasFromAsked(event)
            const pending = ev.callID ? pendingByCall.get(ev.callID) : undefined
            const card = createCard(ev, {
              ...extras,
              ...(pending ? { effect: pending.effect, source_agent: pending.agent ?? null } : {}),
            })
            await writeCard(card)
          } catch (err) {
            console.error(`[decision-queue-hook] permission asked handler failed: ${err}`)
          }
          continue
        }

        if (type === "permission.replied") {
          try {
            const payload = (event?.data ?? event?.properties ?? event ?? {}) as Record<string, any>
            const requestID = payload.requestID ?? payload.permissionID
            const reply = payload.reply ?? payload.response
            if (typeof requestID === "string" && typeof reply === "string") {
              // match строго по requestID — чужие карточки не трогаем
              await appendDecisionToCard(requestID, reply)
            }
          } catch (err) {
            console.error(`[decision-queue-hook] permission replied handler failed: ${err}`)
          }
          continue
        }
      }
    })()

    return () => controller.abort()
  },
})
