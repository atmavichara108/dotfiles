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

// Auto-discovery loads every module in this directory as a plugin and expects
// its default export to be callable. Keep the helper surface on that function
// so CommonJS require() destructuring still exposes the named helpers.
export default Object.assign(async () => ({}), {
  inferRisk,
  sanitizeReason,
  generateCardId,
})
