// telemetry-helpers.ts — TS-шим над рантайм-модулем telemetry-helpers.js
// (паттерн lib/: .js — источник и рантайм, .ts — реэкспорт для типизации,
// как decision-queue-helpers.ts).
export { default } from "./telemetry-helpers.js"
export {
  REDACT_REPLACEMENT,
  REDACT_PATTERNS,
  SECRET_KEY_RE,
  CONTENT_KEY_RE,
  redactString,
  redactFields,
  buildAuditRecord,
  buildTokenRecord,
  estimateTokens,
  appendJsonlRecord,
  readJsonlLines,
  buildReport,
} from "./telemetry-helpers.js"
