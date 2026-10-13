// ~/.config/opencode/plugins/command-observer.ts
// Metadata-only command observer: completed shell calls only, no command content persisted.

import { Plugin } from "@opencode/plugin"
import { appendFileSync, existsSync, mkdirSync, readFileSync } from "node:fs"
import { dirname } from "node:path"

const STATE_PATH = "/home/rudra/.local/state/opencode/command-observations.jsonl"
const NORM_VERSION = 1
const MODULE_THRESHOLD = 3
const SUBAGENT_MODULE_THRESHOLD = 5
const SESSION_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/

// Exact command forms only: no operands, paths, options, or shell syntax.
const SAFE_OPERATIONS = {
  "git status": { operation: "git.status", module: "git-status" },
  "git diff": { operation: "git.diff", module: "git-diff" },
  "git log": { operation: "git.log", module: "git-log" },
  "git branch": { operation: "git.branch", module: "git-branch" },
  "git show": { operation: "git.show", module: "git-show" },
} as const

type Operation = (typeof SAFE_OPERATIONS)[keyof typeof SAFE_OPERATIONS]
type ModuleLabel = Operation["module"]
type ObserverRecord = {
  ts: string
  session_id: string
  event: "tool.execute.after"
  tool: "bash"
  operation: Operation["operation"]
  module: ModuleLabel
  session_count: number
  module_candidate: boolean
  subagent_candidate: boolean
  norm_version: number
}

type ObserverState = {
  counts: Map<string, number>
  candidateModules: Map<string, Set<ModuleLabel>>
  subagentIssued: Set<string>
}

type ObserverContext = {
  tool: { hook: (name: string, callback: (event: unknown) => unknown) => Promise<unknown> }
}

// These are detector patterns, not redactors: a match means skip the event.
// Keep them local so raw args never flow through redactFields or another logger.
const SECRET_MARKERS = [
  /\bsk-[a-z0-9_-]{6,}/i,
  /\bbearer\s+[a-z0-9._~+/=-]+/i,
  /(?:^|[^a-z0-9])(?:api[\s_-]?key|api[\s_-]?token|access[\s_-]?token|auth|authorization|bearer|basic|password|passwd|pwd|secret|token)(?:$|[^a-z0-9])/i,
  /(?:^|[^a-z0-9])client[\s_-]?secret(?:$|[^a-z0-9])/i,
  /\btoken\s*[=:]/i,
  /\b(?:ghp|gho|ghu|ghs|ghr)_[a-z0-9]{20,}\b/i,
  /\bAKIA[0-9A-Z]{16}\b/i,
  /\b(?:A3T[A-Z0-9]|AGPA[A-Z0-9]|AROA[A-Z0-9]|AIDA[A-Z0-9]|ASIA[A-Z0-9])[A-Z0-9]{16}\b/i,
  /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/i,
  /\b(?:bearer|basic)\s+[a-z0-9._~+/=-]{16,}\b/i,
]

const RECORD_KEYS = [
  "ts",
  "session_id",
  "event",
  "tool",
  "operation",
  "module",
  "session_count",
  "module_candidate",
  "subagent_candidate",
  "norm_version",
].sort()

const operationByLabel = new Map<string, Operation>(
  Object.values(SAFE_OPERATIONS).map((entry) => [entry.module, entry]),
)

function newState(): ObserverState {
  return { counts: new Map(), candidateModules: new Map(), subagentIssued: new Set() }
}

function stateKey(sessionId: string, operation: string): string {
  return `${sessionId}\u0000${operation}`
}

function reportFixedError(code: "STATE_READ_FAILED" | "STATE_LINE_INVALID" | "INPUT_PARSE_FAILED" | "SECRET_DETECTOR_FAILED" | "STATE_WRITE_FAILED"): void {
  try {
    console.error(`[command-observer] ${code}`)
  } catch {
    // Logging must never affect the host session.
  }
}

function exactKeys(value: Record<string, unknown>): boolean {
  const keys = Object.keys(value).sort()
  return keys.length === RECORD_KEYS.length && keys.every((key, index) => key === RECORD_KEYS[index])
}

function replayRecord(state: ObserverState, record: unknown): boolean {
  if (record == null || typeof record !== "object" || Array.isArray(record)) return false
  const item = record as Record<string, unknown>
  if (!exactKeys(item)) return false
  if (
    typeof item.ts !== "string" ||
    !Number.isFinite(Date.parse(item.ts)) ||
    new Date(item.ts).toISOString() !== item.ts ||
    typeof item.session_id !== "string" ||
    !SESSION_ID_RE.test(item.session_id) ||
    item.event !== "tool.execute.after" ||
    item.tool !== "bash" ||
    typeof item.operation !== "string" ||
    typeof item.module !== "string" ||
    typeof item.session_count !== "number" ||
    !Number.isSafeInteger(item.session_count) ||
    typeof item.module_candidate !== "boolean" ||
    typeof item.subagent_candidate !== "boolean" ||
    item.norm_version !== NORM_VERSION
  ) return false

  const operation = operationByLabel.get(item.module)
  if (!operation || operation.operation !== item.operation) return false

  const countKey = stateKey(item.session_id, operation.operation)
  const nextCount = (state.counts.get(countKey) ?? 0) + 1
  if (item.session_count !== nextCount) return false

  const modules = new Set(state.candidateModules.get(item.session_id) ?? [])
  const becomesModuleCandidate = nextCount === MODULE_THRESHOLD + 1
  if (item.module_candidate !== becomesModuleCandidate) return false
  if (nextCount > MODULE_THRESHOLD) modules.add(operation.module)

  const subagentKey = item.session_id
  const becomesSubagentCandidate =
    !state.subagentIssued.has(subagentKey) && modules.size >= SUBAGENT_MODULE_THRESHOLD
  if (item.subagent_candidate !== becomesSubagentCandidate) return false

  state.counts.set(countKey, nextCount)
  state.candidateModules.set(item.session_id, modules)
  if (becomesSubagentCandidate) state.subagentIssued.add(subagentKey)
  return true
}

function loadState(path: string): ObserverState | null {
  const state = newState()
  if (!existsSync(path)) return state
  let text: string
  try {
    text = readFileSync(path, "utf8")
  } catch {
    reportFixedError("STATE_READ_FAILED")
    return null
  }
  for (const line of text.split("\n")) {
    if (line === "") continue
    try {
      if (!replayRecord(state, JSON.parse(line))) reportFixedError("STATE_LINE_INVALID")
    } catch {
      reportFixedError("STATE_LINE_INVALID")
    }
  }
  return state
}

function hasSecretMarker(command: string): boolean | null {
  try {
    for (const marker of SECRET_MARKERS) {
      marker.lastIndex = 0
      if (marker.test(command)) return true
    }
    return false
  } catch {
    return null
  } finally {
    for (const marker of SECRET_MARKERS) marker.lastIndex = 0
  }
}

function operationFor(command: string): Operation | undefined {
  return SAFE_OPERATIONS[command.trim() as keyof typeof SAFE_OPERATIONS]
}

function appendRecord(path: string, record: ObserverRecord): void {
  mkdirSync(dirname(path), { recursive: true })
  appendFileSync(path, `${JSON.stringify(record)}\n`, "utf8")
}

/** Register the after-hook; statePath and clock are injectable only for offline tests. */
export async function registerCommandObserver(
  ctx: ObserverContext,
  statePath = STATE_PATH,
  clock: () => Date = () => new Date(),
): Promise<void> {
  let state = loadState(statePath)
  let disabled = state === null

  await ctx.tool.hook("execute.after", async (rawEvent: unknown) => {
    if (disabled || rawEvent == null || typeof rawEvent !== "object") return
    try {
      const event = rawEvent as Record<string, unknown>
      if (event.tool !== "bash") return
      const sessionId = event.sessionID
      if (typeof sessionId !== "string" || !SESSION_ID_RE.test(sessionId)) return

      const input = event.input
      if (input == null || typeof input !== "object" || Array.isArray(input)) {
        reportFixedError("INPUT_PARSE_FAILED")
        return
      }
      const args = input as Record<string, unknown>
      const keys = Object.keys(args)
      if (keys.length !== 1 || keys[0] !== "command" || typeof args.command !== "string") {
        reportFixedError("INPUT_PARSE_FAILED")
        return
      }

      const command = args.command
      const hasSecret = hasSecretMarker(command)
      if (hasSecret === null) {
        reportFixedError("SECRET_DETECTOR_FAILED")
        return
      }
      if (hasSecret) return

      const operation = operationFor(command)
      if (!operation) return

      const countKey = stateKey(sessionId, operation.operation)
      const sessionCount = (state.counts.get(countKey) ?? 0) + 1
      const modules = new Set(state.candidateModules.get(sessionId) ?? [])
      const moduleCandidate = sessionCount === MODULE_THRESHOLD + 1
      if (sessionCount > MODULE_THRESHOLD) modules.add(operation.module)
      const subagentCandidate =
        !state.subagentIssued.has(sessionId) && modules.size >= SUBAGENT_MODULE_THRESHOLD

      const record: ObserverRecord = {
        ts: clock().toISOString(),
        session_id: sessionId,
        event: "tool.execute.after",
        tool: "bash",
        operation: operation.operation,
        module: operation.module,
        session_count: sessionCount,
        module_candidate: moduleCandidate,
        subagent_candidate: subagentCandidate,
        norm_version: NORM_VERSION,
      }

      try {
        appendRecord(statePath, record)
      } catch {
        disabled = true
        reportFixedError("STATE_WRITE_FAILED")
        return
      }
      state.counts.set(countKey, sessionCount)
      state.candidateModules.set(sessionId, modules)
      if (subagentCandidate) state.subagentIssued.add(sessionId)
    } catch {
      // No exception, command, args, output, or path is included in diagnostics.
      reportFixedError("INPUT_PARSE_FAILED")
    }
  })
}

export default Plugin.define({
  id: "command-observer",
  async setup(ctx) {
    try {
      await registerCommandObserver(ctx)
    } catch {
      reportFixedError("INPUT_PARSE_FAILED")
    }
  },
})
