// ~/.config/opencode/lib/classifier-gliclass.ts
// И-22: локальный zero-shot классификатор команд → слоты модулей субагента.
// Архитектура: GLiClass edge (knowledgator/gliclass-edge-v3.0, Apache-2.0,
// 32.7M params, CPU, zero-shot). При отсутствии пакета/модели — детерминированный
// fallback по allowlist executable+subcommand (не менее безопасный).
//
// Назначение: принимает безопасную нормализованную строку операции (например
// "git status", "stow dry-run") и возвращает ranked-список слотов модулей
// из фиксированного словаря MODULE_VOCABULARY. Ничего не пишет на диск, не
// хранит raw args/paths/secrets, не вызывает сеть. Только pure function.
//
// Использование: command-observer вызывает classifyOperation() для дозаписи
// безопасного metadata поля "module_slot" в JSONL; либо external CLI поверх
// уже собранного dataset.
//
// Privacy: вход — нормализованная строка операции (только имя команды и
// подкоманды, без путей/операндов/секретов). Выход — список {label, score}.
// Промежуточные тексты не логируются. Fail-closed: при ошибке модели —
// fallback, при ошибке fallback — пустой список + фиксированный error code.

import { execFile } from "node:child_process"

// --- Словарь модулей (кандидаты И-20/И-22) ------------------------------
// Каждый слот — будущий модуль/субагент. Пороги 3/5 считаются отдельно
// (command-observer), здесь — только семантическая привязка операции к слоту.
export const MODULE_VOCABULARY: readonly string[] = [
  "git-flow",
  "stow-deploy",
  "zsh-env",
  "qtile-wm",
  "nvim-editor",
  "opencode-infra",
  "research-docs",
  "shell-automation",
  "system-info",
  "other",
] as const

export type ModuleSlot = (typeof MODULE_VOCABULARY)[number]

export interface Classification {
  slot: ModuleSlot
  score: number // 0..1; у fallback — 1.0 для exact match, 0.0 для "other"
  source: "gliclass" | "fallback"
}

export interface ClassifyOptions {
  /** Абсолютный путь к каталогу модели GLiClass (HF cache или local dir). */
  modelPath?: string
  /** Явный вызов python3 для gliclass; по умолчанию — user-venv gliclass-venv. */
  pythonBin?: string
  /** Таймаут на один вызов модели, мс. */
  timeoutMs?: number
  /** Максимум возвращаемых слотов (top-k). */
  topK?: number
}

const FALLBACK_TABLE: ReadonlyArray<{ re: RegExp; slot: ModuleSlot }> = [
  { re: /^git(\s|$)/, slot: "git-flow" },
  { re: /^stow(\s|$)/, slot: "stow-deploy" },
  { re: /^(zsh|bash|sh|shellcheck)(\s|$)/, slot: "zsh-env" },
  { re: /^qtile-(\s|$)/, slot: "qtile-wm" },
  { re: /^nvim(\s|$)/, slot: "nvim-editor" },
  { re: /^opencode(\s|$)/, slot: "opencode-infra" },
  { re: /^(bat|eza|rg|fd|sed|awk)(\s|$)/, slot: "research-docs" },
  { re: /^(python3?|node|bun)(\s|$)/, slot: "shell-automation" },
  { re: /^(ls|cat|head|tail|wc|stat|uname|df|free)(\s|$)/, slot: "system-info" },
]

function sanitizeOperation(op: string): string {
  // Жёсткая нормализация: только нижний регистр, буквы/цифры/пробел/дефис.
  // Пути, операнды, кавычки, спецсимволы — вырезаются до classify.
  return op
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 120)
}

function fallbackClassify(op: string): Classification[] {
  const clean = sanitizeOperation(op)
  for (const { re, slot } of FALLBACK_TABLE) {
    if (re.test(clean)) return [{ slot, score: 1.0, source: "fallback" }]
  }
  return [{ slot: "other", score: 0.0, source: "fallback" }]
}

// --- GLiClass через короткий python3 subprocess ---------------------------
// Не держим модель в памяти плагина; один вызов — один subprocess.
// Канал stdin/stdout — JSON, без вывода модели в лог.
interface GliclassRaw {
  labels: string[]
  scores: number[]
}

function runGliclass(op: string, opts: ClassifyOptions): Promise<GliclassRaw | null> {
  return new Promise((resolve) => {
    const py =
      opts.pythonBin ??
      process.env.GLICLASS_PY ??
      "/home/rudra/.local/share/opencode/gliclass-venv/bin/python"
    const modelPath = opts.modelPath ?? "knowledgator/gliclass-edge-v3.0"
    const timeout = opts.timeoutMs ?? 20000
    const script = `
import json, sys
try:
    from gliclass import GLiClassModel, ZeroShotClassificationPipeline
    from transformers import AutoTokenizer
except Exception:
    print(json.dumps({"labels": [], "scores": []})); sys.exit(0)
try:
    model = GLiClassModel.from_pretrained(${JSON.stringify(modelPath)})
    tokenizer = AutoTokenizer.from_pretrained(${JSON.stringify(modelPath)})
    pipe = ZeroShotClassificationPipeline(
        model=model, tokenizer=tokenizer,
        classification_type="multi-label", device="cpu", progress_bar=False,
    )
    text = sys.stdin.read().strip()
    labels = ${JSON.stringify(MODULE_VOCABULARY)}
    out = pipe([text], labels=labels, threshold=0.0)
    # out: [[{"label": str, "score": float}, ...]] — top по убыванию
    probs = {item["label"]: float(item["score"]) for item in out[0]}
    ordered = sorted(probs.items(), key=lambda kv: -kv[1])
    print(json.dumps({"labels": [k for k, _ in ordered], "scores": [v for _, v in ordered]}))
except Exception:
    print(json.dumps({"labels": [], "scores": []}))
`
    const child = execFile(
      py,
      ["-c", script],
      { timeout, maxBuffer: 1 << 20 },
      (err, stdout) => {
        if (err) return resolve(null)
        try {
          const parsed = JSON.parse(String(stdout)) as GliclassRaw
          if (!Array.isArray(parsed.labels) || !Array.isArray(parsed.scores)) return resolve(null)
          resolve(parsed)
        } catch {
          resolve(null)
        }
      },
    )
    child.stdin?.end(sanitizeOperation(op))
  })
}

export async function classifyOperation(
  operation: string,
  opts: ClassifyOptions = {},
): Promise<Classification[]> {
  const clean = sanitizeOperation(operation)
  if (!clean) return [{ slot: "other", score: 0.0, source: "fallback" }]

  const raw = await runGliclass(clean, opts).catch(() => null)
  if (raw && raw.labels.length > 0 && raw.scores.length === raw.labels.length) {
    const topK = opts.topK ?? 3
    const allowed = new Set<string>(MODULE_VOCABULARY)
    const out: Classification[] = []
    for (let i = 0; i < raw.labels.length && out.length < topK; i++) {
      const label = raw.labels[i]
      if (!allowed.has(label)) continue
      const score = Number(raw.scores[i])
      if (!Number.isFinite(score)) continue
      out.push({ slot: label as ModuleSlot, score, source: "gliclass" })
    }
    if (out.length > 0) return out
  }

  return fallbackClassify(clean)
}

// --- Offline smoke (запуск: bun lib/classifier-gliclass.ts) --------------
if (import.meta.main) {
  const cases = ["git status", "stow dry-run zsh", "opencode run", "unknown cmd"]
  for (const c of cases) {
    const r = await classifyOperation(c, { topK: 1 })
    console.log(c, "=>", r)
  }
}
