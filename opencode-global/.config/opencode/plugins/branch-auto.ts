// ~/.config/opencode/plugins/branch-auto.ts
// Авто-ветка от темы сессии: каждый новый тематический запрос (новая сессия)
// получает собственную git-ветку task/<slug> — вместо работы в чужой ветке
// и конфликтов при параллельной работе.
//
// Механика (V2-примитивы, проверены по соседним плагинам):
//   session.created    → ctx.event.subscribe() (как session-flush.ts):
//                        запоминаем { sessionID → directory } для определения
//                        репозитория сессии.
//   session.text.ended → первое сообщение сессии (первый text.ended для
//                        sessionID): data.text → slug, создаём ветку.
//
// Правила создания:
//   1. Только в git-репозитории (git rev-parse --show-toplevel успешен).
//   2. Только если текущая ветка НЕ task/* (уже в рабочей ветке — не дублируем).
//   3. Только если дерево чистое (git status --porcelain пуст) — иначе не
//      переключаемся, только предупреждаем (не трогаем чужие правки).
//   4. База: origin/main → fallback main → текущая HEAD.
//   5. Имя: task/<slug>, slug из темы первого сообщения (кириллица →
//      транслитерация, мусор вырезается).
//
// Обход (осознанный): BRANCH_AUTO=0 в окружении.
// Fail-open: любая ошибка логируется и НЕ ломает сессию.
//
// Формат: V2 (OpenCode 2.0.18), как main-protector.ts / tree-hygiene.ts.

import { Plugin } from "@opencode/plugin"
import { execFile } from "node:child_process"

const SESSION_CREATED = "session.created"
const TEXT_ENDED = "session.text.ended"

// --- утилиты git (promisify execFile) --------------------------------------
function git(args: string[], cwd: string): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile("git", args, { cwd }, (err, stdout) =>
      err ? reject(err) : resolve(stdout.trim()),
    )
  })
}

async function isGitRepo(directory: string): Promise<boolean> {
  try {
    await git(["rev-parse", "--show-toplevel"], directory)
    return true
  } catch {
    return false
  }
}

async function currentBranch(directory: string): Promise<string | null> {
  try {
    return await git(["rev-parse", "--abbrev-ref", "HEAD"], directory)
  } catch {
    return null
  }
}

async function isDirty(directory: string): Promise<boolean> {
  try {
    const out = await git(["status", "--porcelain"], directory)
    return out.length > 0
  } catch {
    return false // fail-open: не уверены — считаем чисто
  }
}

async function hasRemoteMain(directory: string): Promise<boolean> {
  try {
    await git(["rev-parse", "--verify", "origin/main"], directory)
    return true
  } catch {
    return false
  }
}

// --- slug из темы -----------------------------------------------------------
const TRANSLIT: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z",
  и: "i", й: "y", к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r",
  с: "s", т: "t", у: "u", ф: "f", х: "h", ц: "ts", ч: "ch", ш: "sh",
  щ: "sch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya",
}

function slugify(text: string): string {
  const lower = text.toLowerCase()
  let out = ""
  for (const ch of lower) {
    if (TRANSLIT[ch] !== undefined) out += TRANSLIT[ch]
    else if (/[a-z0-9]/.test(ch)) out += ch
    else if (/[\s\-_]/.test(ch)) out += "-"
    // остальное (пунктуация, спецсимволы) — пропускаем
  }
  out = out.replace(/-{2,}/g, "-").replace(/^-|-$/g, "")
  // оставляем до 6 значимых слов
  const words = out.split("-").filter(Boolean).slice(0, 6)
  return words.join("-") || "task"
}

// --- состояние --------------------------------------------------------------
interface Pending {
  directory?: string
  branchDone: boolean
}

export default Plugin.define({
  id: "branch-auto",
  async setup(ctx) {
    const sessions = new Map<string, Pending>()
    const controller = new AbortController()

    const createBranch = async (sessionID: string, text: string) => {
      const entry = sessions.get(sessionID)
      if (!entry || entry.branchDone) return
      if (process.env.BRANCH_AUTO === "0") return
      const directory = entry.directory
      if (!directory) return

      try {
        if (!(await isGitRepo(directory))) return
        const branch = await currentBranch(directory)
        if (branch && branch.startsWith("task/")) {
          // уже в рабочей ветке — не дублируем
          entry.branchDone = true
          return
        }
        if (await isDirty(directory)) {
          console.log(
            `[branch-auto] сессия ${sessionID}: дерево грязное — ветку НЕ создаю, ` +
            `чтобы не трогать чужие правки. Тема: ${text.slice(0, 80)}`,
          )
          entry.branchDone = true // повторно не дёргаем
          return
        }

        const slug = slugify(text)
        const branchName = `task/${slug}`
        const base = (await hasRemoteMain(directory))
          ? "origin/main"
          : "main"

        await git(["switch", "-c", branchName, base], directory)
        console.log(
          `[branch-auto] сессия ${sessionID}: создана ветка ${branchName} от ${base} ` +
          `(тема: ${text.slice(0, 80)})`,
        )
        entry.branchDone = true
      } catch (err) {
        console.error(`[branch-auto] create failed for ${sessionID}: ${err}`)
        // не помечаем done — может, следующий промпт будет чище
      }
    }

    void (async () => {
      for await (const raw of ctx.event.subscribe({ signal: controller.signal })) {
        const event = raw as unknown as {
          type?: string
          sessionID?: string
          data?: { sessionID?: string; text?: string; ordinal?: number; location?: { directory?: string } }
        }
        try {
          if (event.type === SESSION_CREATED) {
            const sessionID = event.data?.sessionID ?? event.sessionID
            if (!sessionID) continue
            const directory = event.data?.location?.directory
            sessions.set(sessionID, { directory, branchDone: false })
            continue
          }
          if (event.type === TEXT_ENDED) {
            const sessionID = event.data?.sessionID ?? event.sessionID
            const text = event.data?.text ?? ""
            if (!sessionID || !text.trim()) continue
            // инициализируем, если session.created не видели (например,
            // плагин поднялся на уже живой сессии)
            if (!sessions.has(sessionID)) {
              sessions.set(sessionID, { branchDone: false })
            }
            await createBranch(sessionID, text)
          }
        } catch (err) {
          console.error(`[branch-auto] event handling failed: ${err}`)
        }
      }
    })()

    return () => controller.abort()
  },
})