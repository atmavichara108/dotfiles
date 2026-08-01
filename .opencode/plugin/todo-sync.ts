import type { Plugin } from "@opencode-ai/plugin"
import type { Todo } from "@opencode-ai/sdk"
import { readFile, writeFile, mkdir } from "node:fs/promises"
import { dirname } from "node:path"

export default (async ({ directory }) => {
  const todoMemoryPath = `${directory}/.opencode/memory/todo.json`
  let todosSnapshot: Todo[] = []

  const loadTodos = async () => {
    try {
      const content = await readFile(todoMemoryPath, "utf-8")
      todosSnapshot = JSON.parse(content)
    } catch {
      todosSnapshot = []
    }
  }

  const saveTodos = async () => {
    await mkdir(dirname(todoMemoryPath), { recursive: true })
    await writeFile(todoMemoryPath, JSON.stringify(todosSnapshot, null, 2))
  }

  return {
    config: async () => {
      await loadTodos()
    },

    "tool.execute.after": async (input, output) => {
      if (input.tool !== "task") return

      const agentName = input.args?.agent || input.args?.subagent_type || ""
      if (!agentName) return

      const isError =
        output.output?.toLowerCase().includes("error") ||
        output.metadata?.error

      const todo = todosSnapshot.find((t) => {
        if (t.status !== "in_progress") return false
        return t.content.toLowerCase().includes(agentName.toLowerCase())
      })

      if (todo) {
        todo.status = isError ? "failed" : "completed"
        await saveTodos()
      }
    },

    event: async ({ event }) => {
      if (event.type === "file.edited") {
        const file = event.properties.file
        if (file.includes(".opencode/memory/decisions.md")) {
          await loadTodos()
        }
      }
      if (event.type === "todo.updated") {
        todosSnapshot = event.properties.todos
        await saveTodos()
      }
    },
  }
}) satisfies Plugin
