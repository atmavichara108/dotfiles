// Enforce project-directed execution-spec writes at the tool boundary.
// A skill explains routing; this hook prevents the common Vault-staging mistake.
import type { Plugin } from "@opencode-ai/plugin"
import path from "path"

const ROUTES: Record<string, string> = {
  vault: "/home/rudra/Projects/OpenCode-Vault/docs/specs",
  dotfiles: "/home/rudra/dotfiles/docs/specs",
  "dv-hub": "/home/rudra/Projects/dv-hub/docs/specs",
  AndroidOS: "/home/rudra/Projects/AndroidOS/docs/specs",
  ChaT: "/home/rudra/Projects/ChaT/docs/specs",
  SERPlux: "/home/rudra/Projects/serp/docs/specs",
}

function text(value: unknown): string {
  try { return JSON.stringify(value) } catch { return String(value ?? "") }
}

function projectOf(args: unknown): string | null {
  const match = text(args).match(/(?:^|["'\s])project\s*:\s*([A-Za-z0-9_-]+)/i)
  return match?.[1] ?? null
}

function pathsOf(args: unknown): string[] {
  const found: string[] = []
  const walk = (value: unknown) => {
    if (typeof value === "string" && (value.startsWith("/") || value.startsWith("~"))) found.push(value)
    else if (Array.isArray(value)) value.forEach(walk)
    else if (value && typeof value === "object") Object.values(value).forEach(walk)
  }
  walk(args)
  return found
}

const plugin: Plugin = async () => ({
  "tool.execute.before": async (input: any, output: any) => {
    const tool = String(input?.tool ?? input?.name ?? "").toLowerCase()
    if (tool !== "edit" && tool !== "write") return
    const args = output?.args ?? input?.args
    const project = projectOf(args)
    if (!project || !ROUTES[project]) return
    const expected = path.resolve(ROUTES[project])
    const paths = pathsOf(args).map(path.resolve)
    const vaultSpec = "/home/rudra/Projects/OpenCode-Vault/docs/specs"
    if (project !== "vault" && paths.some((p) => p === vaultSpec || p.startsWith(`${vaultSpec}/`))) {
      throw new Error(`BLOCKED: spec for project ${project} must be written to ${expected}, not Vault docs/specs`)
    }
    if (paths.length > 0 && !paths.some((p) => p === expected || p.startsWith(`${expected}/`))) {
      throw new Error(`BLOCKED: spec for project ${project} must be written inside ${expected}`)
    }
  },
})

export default plugin
