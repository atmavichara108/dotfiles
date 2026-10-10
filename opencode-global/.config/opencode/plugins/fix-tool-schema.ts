// ~/.config/opencode/plugins/fix-tool-schema.ts
// Защита схем тулов от Anthropic-совместимых провайдеров (justwoker/claude-*):
// API отвергает input_schema с верхнеуровневым oneOf/anyOf/allOf, а встроенные
// схемы (особенно skill) строятся через union. Мутируем схемы ПЕРЕД вызовом
// модели — прямой эквивалент V1-хука tool.definition.
//
// Порт с V1 (Vault .opencode/plugins/, форма `export default (async () => ...)`):
//   V2 требует `Plugin.define({ id, setup })`; мутация схем — хук
//   session.hook("context")/("compaction")/("generate"): событие несёт
//   event.tools (description + input) и выполняется непосредственно перед
//   отправкой запроса. Поведение идентично V1: skill → плоская схема,
//   остальные → сглаживание корневого union без required.
//
//   V2-фикс (2026-10-10): ядро V2 ждёт у тула skill поле `id`
//   (доки: вызов {"id": "<skill-id>"}), а старая SKILL_FLAT слала `name` —
//   модель звала тул без id и валидатор отвечал `id Missing key`.
//   Новая схема плоская (без oneOf — strict-провайдеры её бы отвергли),
//   требует `id`, `name` оставлен deprecated-алиасом.
//
// Глобальное размещение: подхватывается во всех проектах (в отличие от
// старой копии в Vault, которая грузилась только там и упиралась в V1-форму).

import { Plugin } from "@opencode/plugin"

type Json = Record<string, any>

const SKILL_FLAT: Json = {
  type: "object",
  properties: {
    id: {
      type: "string",
      description: "The exact ID of the skill from available_skills (e.g. \"tree-hygiene\").",
    },
    name: {
      type: "string",
      description:
        "Deprecated alias for id (pre-V2 schema). Prefer id; if both are sent, id wins.",
    },
  },
  required: ["id"],
  additionalProperties: false,
}

function isRecord(v: unknown): v is Json {
  return !!v && typeof v === "object" && !Array.isArray(v)
}

function flattenRootUnion(schema: Json): Json | undefined {
  const branches = schema.oneOf ?? schema.anyOf ?? schema.allOf
  if (!Array.isArray(branches) || branches.length === 0) return undefined
  if (!branches.every((b) => isRecord(b) && (b.type === undefined || b.type === "object"))) {
    return undefined
  }
  const properties: Json = {}
  for (const branch of branches) {
    const props = branch.properties
    if (!isRecord(props)) continue
    for (const [key, value] of Object.entries(props)) {
      if (!isRecord(value) || value.type === "never") continue
      const existing = properties[key]
      if (existing === undefined || (isRecord(existing) && existing.type === "never")) {
        properties[key] = value
      }
    }
  }
  if (Object.keys(properties).length === 0) return undefined
  const out: Json = { ...schema, type: "object", properties, additionalProperties: false }
  delete out.oneOf
  delete out.anyOf
  delete out.allOf
  delete out.required
  return out
}

function fixTools(tools: Record<string, { description: string; input: Json }>): void {
  for (const [name, tool] of Object.entries(tools)) {
    if (!isRecord(tool?.input)) continue
    if (name === "skill") {
      tool.input = SKILL_FLAT
      continue
    }
    const flat = flattenRootUnion(tool.input)
    if (flat) tool.input = flat
  }
}

export default Plugin.define({
  id: "fix-tool-schema",
  async setup(ctx) {
    const handler = (event: { tools: Record<string, { description: string; input: Json }> }) => {
      try {
        fixTools(event.tools)
      } catch (err) {
        console.error(`[fix-tool-schema] failed: ${err}`)
      }
    }
    // Все виды запросов, которые несут тулы (title — без тулов, его не трогаем).
    await ctx.session.hook("context", handler)
    await ctx.session.hook("compaction", handler)
    await ctx.session.hook("generate", handler)
  },
})
