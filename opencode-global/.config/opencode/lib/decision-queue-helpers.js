// Pure helper functions for decision-queue-hook (JavaScript version for smoke test)
// Shared between plugin and smoke test to ensure consistency
// No runtime dependencies, no side effects

// Risk inference from permission type/pattern (metadata-only, no content inspection)
// Uses real SDK fields: type (e.g. "edit", "bash", "task") and pattern (e.g. "git push", "external_directory")
export function inferRisk(type, pattern) {
  const typeLower = (type || "").toLowerCase()
  const patternLower = (pattern || "").toLowerCase()

  // Critical: destructive git, system mutations
  if (
    patternLower.includes("push") ||
    patternLower.includes("force") ||
    patternLower.includes("reset") ||
    patternLower.includes("clean") ||
    (typeLower.includes("bash") && (patternLower.includes("sudo") || patternLower.includes("rm")))
  ) {
    return "critical"
  }

  // High: git write, file mutations, external directory
  if (
    patternLower.includes("git") ||
    typeLower.includes("edit") ||
    typeLower.includes("write") ||
    patternLower.includes("edit") ||
    patternLower.includes("external_directory")
  ) {
    return "high"
  }

  // Medium: task dispatch, network
  if (
    typeLower.includes("task") ||
    typeLower.includes("webfetch") ||
    typeLower.includes("websearch") ||
    patternLower.includes("task")
  ) {
    return "medium"
  }

  // Low: read-only, validation
  return "low"
}

// Sanitize reason: strip potential secrets, prompts, tool output
export function sanitizeReason(reason) {
  if (!reason) return "Permission event captured"

  // Truncate to bounded length
  let sanitized = reason.slice(0, 200)

  // Strip common secret patterns (API keys, tokens, passwords)
  // Includes "api key" with space, "api_key", "api-key"
  sanitized = sanitized
    .replace(/(?:api[_\s-]?key|token|password|secret|auth)[\s:=]+[^\s,;]+/gi, "[REDACTED]")
    .replace(/(?:sk-|ghp_|github_pat_)[a-z0-9]{10,}/gi, "[REDACTED]")
    .replace(/Bearer\s+[^\s]+/gi, "[REDACTED]")

  // Strip file paths that might contain sensitive info (keep only filename)
  sanitized = sanitized.replace(/\/home\/[^\s]+/g, "[PATH]")
  sanitized = sanitized.replace(/\/Users\/[^\s]+/g, "[PATH]")

  return sanitized.trim() || "Permission event captured"
}

// Generate card ID from timestamp + slug
export function generateCardId(type, pattern) {
  const now = new Date()
  const dateStr = now.toISOString().split("T")[0] // YYYY-MM-DD
  const timeStr = now.toTimeString().split(" ")[0].replace(/:/g, "") // HHMMSS

  const slug = (type || pattern || "permission")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 30)

  return `${dateStr}-${timeStr}-${slug}`
}

// --- Теневой классификатор решений (ADR-022) -------------------------------
// Детерминированный zero-LLM classify. Два класса РЕШЕНИЙ (не рантайм-обход):
//   substantive    — сущностные (разрушение, привилегии, секреты, сеть, прод):
//                    только человек, карточка без предложения правила;
//   nomenclatural  — номенклатурные: карточка + proposed_glob для патча конфига
//                    (одно ДА человека на ПРАВИЛО, не на событие).
// Сомнение (пустой/непонятный вход) всегда трактуется в пользу substantive.
export const SUBSTANTIVE_PATTERNS = [
  { name: "rm", re: /\brm\b/ },
  { name: "rmdir", re: /\brmdir\b/ },
  { name: "dd", re: /\bdd\b/ },
  { name: "mkfs", re: /\bmkfs\b/ },
  { name: "chmod", re: /\bchmod\b/ },
  { name: "chown", re: /\bchown\b/ },
  { name: "sudo", re: /\bsudo\b/ },
  { name: "ssh", re: /\bssh\b/ },
  { name: "curl", re: /\bcurl\b/ },
  { name: "wget", re: /\bwget\b/ },
  { name: "systemctl", re: /\bsystemctl\b/ },
  { name: "git-push-force", re: /\bgit\s+push\s+--force/ },
  { name: "git-reset-hard", re: /\bgit\s+reset\s+--hard/ },
  { name: "git-clean", re: /\bgit\s+clean\b/ },
  { name: "dotenv", re: /\.env\b/ },
  { name: "pem", re: /\.pem\b/ },
  { name: "keyfile", re: /\.key\b|id_rsa|id_ed25519/ },
  { name: "secret-path", re: /secret|credential|passw|\.netrc/ },
]

// classify(action, resources[, save]) → { class, rationale, proposed_glob }
// Чистая функция: без LLM, без side effects, детерминирована по входу.
export function classify(action, resources, save = []) {
  const parts = [action, ...(Array.isArray(resources) ? resources : [])]
    .map((x) => (typeof x === "string" ? x : ""))
    .join(" ")
    .toLowerCase()
    .trim()

  if (!parts) {
    return {
      class: "substantive",
      rationale: "пустой или нераспознанный вход — сомнение в пользу человека",
      proposed_glob: null,
    }
  }

  for (const { name, re } of SUBSTANTIVE_PATTERNS) {
    if (re.test(parts)) {
      return {
        class: "substantive",
        rationale: `совпал сущностный паттерн «${name}»`,
        proposed_glob: null,
      }
    }
  }

  const glob = Array.isArray(save) && save.length > 0 && typeof save[0] === "string" ? save[0] : null
  return {
    class: "nomenclatural",
    rationale: "нет совпадений с substantive-паттернами",
    proposed_glob: glob,
  }
}

// Parse a card file's last JSON document (pretty-printed JSON or JSONL history).
// Used for strict append-on-reply without rewriting unknown records blindly.
export function parseLastJson(raw) {
  if (!raw || typeof raw !== "string") return null
  try {
    return JSON.parse(raw)
  } catch {
    // многострочная/несколько записей — читаем последнюю JSON-строку снизу
  }
  const lines = raw.split("\n").filter((l) => l.trim())
  for (let i = lines.length - 1; i >= 0; i--) {
    try {
      return JSON.parse(lines[i])
    } catch {
      // пропускаем мусор, идём выше
    }
  }
  return null
}

// Merge a human decision into the last card document (strict by-id append-on-reply).
// Pure: returns the merged record or null when the base is unparsable.
// status/reply mapping: once/always -> approved, reject -> denied.
export function mergeDecisionIntoCard(last, requestID, decision, timestamp) {
  if (!last || typeof last !== "object") return null
  const approved = decision === "once" || decision === "always"
  return {
    ...last,
    id: last.id || requestID,
    updated: timestamp,
    status: approved ? "approved" : "denied",
    decision,
  }
}

// Auto-discovery loads every module in this directory as a plugin and expects
// its default export to be callable. Keep the helper surface on that function
// so CommonJS require() destructuring still exposes the named helpers.
export default Object.assign(async () => ({}), {
  inferRisk,
  sanitizeReason,
  generateCardId,
  classify,
  parseLastJson,
})
