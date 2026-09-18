// ~/.config/opencode/plugins/decision-queue-hook.ts
// Decision Queue runtime hook: metadata-only card creation on permission events.
// No shell/git/network/file edit actions. Append-only JSONL output.
// Canonical Vault storage if runtime path permitted; otherwise explicit fallback.

import type { Plugin } from "@opencode-ai/plugin"
import { appendFile, mkdir } from "fs/promises"
import { join } from "path"
import { existsSync } from "fs"
import { inferRisk, sanitizeReason, generateCardId } from "./decision-queue-helpers.js"

// Type declarations for imported JS helpers (TypeScript needs types)

// Real OpenCode Plugin SDK permission.ask payload fields (2026-09-05):
// id, type, pattern, sessionID, messageID, callID, title, metadata, time
// Fallback: use event catch-all if permission.ask not available.
// Metadata extraction best-effort; missing fields → "unknown" placeholder.

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

interface DecisionCard {
  id: string
  created: string
  updated: string
  status: "pending" | "approved" | "rejected" | "deferred" | "resolved"
  risk: "low" | "medium" | "high" | "critical"
  source: {
    agent: string
    session: string
    trigger: "permission.asked" | "tool.blocked" | "unroutable" | "acceptance.gate" | "manual"
    tool?: string
    permission?: string
    directory?: string
    messageID?: string
    callID?: string
  }
  dilemma: {
    title: string
    context: string
    options: Array<{ id: string; label: string; pros: string[]; cons: string[] }>
    recommendation: string | null
    reason: string
  }
  resolution: {
    choice: string | null
    approved_by: string | null
    approved_at: string | null
    evidence: string | null
  }
  stop_condition: string
}

// Create metadata-only decision card
function createCard(event: PermissionEvent): DecisionCard {
  const type = event.type || "unknown"
  const pattern = event.pattern || "unknown"
  const sessionID = event.sessionID || "unknown"
  const messageID = event.messageID || "unknown"
  const callID = event.callID || "unknown"
  const title = event.title || `Permission event: ${type}`
  const time = event.time || new Date().toISOString()
  
  // Extract reason from metadata if available, otherwise use title
  const reason = sanitizeReason(
    (event.metadata?.reason as string) || event.title || "Permission event captured"
  )
  const risk = inferRisk(type, pattern)

  const context = `Permission ${type} (pattern: ${pattern}) in session ${sessionID}`

  // Placeholder options (user resolves via /decisions command)
  const options = [
    {
      id: "A",
      label: "Allow this time",
      pros: ["Unblocks current operation"],
      cons: ["May not align with policy"]
    },
    {
      id: "B",
      label: "Deny and review",
      pros: ["Safe default", "Requires policy review"],
      cons: ["Blocks operation"]
    },
    {
      id: "C",
      label: "Update policy",
      pros: ["Permanent fix"],
      cons: ["Requires config change"]
    }
  ]

  return {
    id: generateCardId(type, pattern),
    created: time,
    updated: time,
    status: "pending",
    risk,
    source: {
      agent: "runtime",
      session: sessionID,
      trigger: "permission.asked",
      tool: type,
      permission: pattern,
      directory: "unknown",
      messageID,
      callID
    },
    dilemma: {
      title,
      context,
      options,
      recommendation: null, // No auto-recommendation (requires human judgment)
      reason
    },
    resolution: {
      choice: null,
      approved_by: null,
      approved_at: null,
      evidence: null
    },
    stop_condition: "after user decision via /decisions command"
  }
}

function normalizePermission(input: PermissionEvent | { permission?: PermissionEvent }): PermissionEvent {
  if ("permission" in input && input.permission) return input.permission
  return input as PermissionEvent
}

const plugin: Plugin = async ({ client, directory }) => {
  // Storage: canonical Vault path only. No fallback to project root.
  // If Vault path not permitted, log only — do not write to arbitrary project dirs.
  // [проверить] external_directory permissions for Vault path not confirmed
  const vaultPath = join(directory, "control-plane", "decision-queue")
  const storagePath = existsSync(vaultPath) ? vaultPath : null
  const logPath = storagePath ? join(storagePath, "runtime-events.jsonl") : null

  client.app.log({
    body: {
      service: "decision-queue-hook",
      level: "info",
      message: storagePath
        ? `initialized, storage: ${storagePath}`
        : "initialized, Vault path not accessible — cards will be logged only, not persisted"
    }
  })

  return {
    // Real SDK hook: permission.ask with actual payload signature
    "permission.ask": async (input: PermissionEvent | { permission?: PermissionEvent }) => {
      try {
        const card = createCard(normalizePermission(input))

        if (!storagePath || !logPath) {
          // No writable path — log card metadata only, do not write to project root
          client.app.log({
            body: {
              service: "decision-queue-hook",
              level: "warn",
              message: `card created (log-only, no storage): ${card.id} (risk: ${card.risk})`
            }
          })
          return
        }

        // Ensure directory exists
        await mkdir(storagePath, { recursive: true })

        // Append-only JSONL output (one card per line)
        const line = JSON.stringify(card) + "\n"
        await appendFile(logPath, line, "utf-8")

        client.app.log({
          body: {
            service: "decision-queue-hook",
            level: "info",
            message: `card created: ${card.id} (risk: ${card.risk})`
          }
        })
      } catch (err) {
        // Don't crash session — log error
        client.app.log({
          body: {
            service: "decision-queue-hook",
            level: "error",
            message: `card creation failed: ${err}`
          }
        })
      }
    },

    // Fallback: event catch-all for permission-related events
    // Real SDK form: input.event.type and input.event.properties
    // [проверить] If permission.ask hook not available, this catches permission events
    event: async (input: { event?: { type?: string; properties?: Record<string, unknown> } }) => {
      // Safely read real SDK form: input.event.type and input.event.properties
      const eventType = input?.event?.type || ""
      const eventProperties = input?.event?.properties || {}

      // Only process permission-related events
      if (
        eventType.includes("permission") ||
        eventType.includes("blocked") ||
        eventType.includes("ask")
      ) {
        try {
          // Convert properties to PermissionEvent shape
          const permEvent: PermissionEvent = {
            id: eventProperties.id as string,
            type: (eventProperties.type as string) || eventType,
            pattern: eventProperties.pattern as string,
            sessionID: eventProperties.sessionID as string,
            messageID: eventProperties.messageID as string,
            callID: eventProperties.callID as string,
            title: eventProperties.title as string,
            metadata: eventProperties.metadata as Record<string, unknown>,
            time: eventProperties.time as string
          }

          const card = createCard(permEvent)

          if (!storagePath || !logPath) {
            client.app.log({
              body: {
                service: "decision-queue-hook",
                level: "warn",
                message: `card created (fallback, log-only, no storage): ${card.id} (risk: ${card.risk})`
              }
            })
            return
          }

          await mkdir(storagePath, { recursive: true })

          const line = JSON.stringify(card) + "\n"
          await appendFile(logPath, line, "utf-8")

          client.app.log({
            body: {
              service: "decision-queue-hook",
              level: "info",
              message: `card created (fallback): ${card.id} (risk: ${card.risk})`
            }
          })
        } catch (err) {
          client.app.log({
            body: {
              service: "decision-queue-hook",
              level: "error",
              message: `card creation failed (fallback): ${err}`
            }
          })
        }
      }
    }
  }
}

export default plugin
