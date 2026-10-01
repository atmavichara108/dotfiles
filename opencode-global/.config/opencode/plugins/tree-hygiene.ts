// ~/.config/opencode/plugins/tree-hygiene.ts
// Принуждение к чистому дереву при параллельной работе (правило фазы 4).
// Дополняет main-protector (тот держит main-коммиты и hot-files):
//   tree-hygiene — грязное дерево НЕ переживает смену ветки/контекста.
//
// Что блокирует (tool.execute.before):
//   1. `git switch` / `git checkout <ref>` при грязном worktree → throw:
//      агент обязан закоммитить свой сюжет в task-ветку или уложить в stash
//      ДО переключения. Иначе работы разных потоков слипаются в чужой ветке.
//   2. `git stash push` без `-m` при грязном дереве → throw: stash без
//      сообщения = безымянный мусор, из которого потом не разобрать сюжеты.
//   3. `git commit` в ветку, заявленную ДРУГОЙ живой сессией → throw:
//      сверка с реестром владения (git-config чекаута, общий для opencode,
//      mcode и человека). Своя ветка — всегда можно; чужая свежая заявка —
//      только с CLAIM_OK=1 в команде (осознанный обход, как MIXED_OK).
//
// Реестр: branch.<name>.owner = sessionID, branch.<name>.claimedAt = epoch.
// Пишут: branch-auto (при создании ref) и этот же гейт (при switch).
// TTL заявки — 24ч (как heartbeat ADR-014): протухла — чужой больше нет.
// Fail-open: любая ошибка разведки → разрешить (как main-protector).
//
// Обход (осознанный): TREE_HYGIENE=1 в окружении.
// Формат: V2 (OpenCode 2.0.18). После апгрейда рантайма остальные плагины
// мигрируются в этот же формат (см. main-protector.ts).

import { Plugin } from "@opencode/plugin"
import { execFile } from "node:child_process"

const SWITCH_RE = /\bgit\s+(switch|checkout)\b(?![^\n]*\s--\s)/
const HAS_REF_RE = /\bgit\s+(switch|checkout)\s+(-[a-zA-Z]+\s+)*([a-zA-Z0-9_./-]+)/
const STASH_RE = /\bgit\s+stash\s+push\b/
const COMMIT_RE = /\bgit\s+commit\b/
const CLAIM_TTL_SEC = 24 * 60 * 60 // как heartbeat ADR-014

function sh(args: string[], cwd: string): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile("git", args, { cwd }, (err, out) =>
      err ? reject(err) : resolve(String(out).trim()),
    )
  })
}

async function currentBranchName(directory: string): Promise<string | null> {
  try {
    const br = await sh(["symbolic-ref", "--short", "-q", "HEAD"], directory)
    return br || null
  } catch {
    return null
  }
}

// Запись владения при переключении. Только ветки (не main/master, не SHA).
// Fail-open: реестр — помощь, throw только у гейтов ниже.
async function claimOnSwitch(directory: string, ref: string, sessionID: string): Promise<void> {
  try {
    if (!sessionID) return
    if (ref === "main" || ref === "master") return
    if (/^[0-9a-f]{7,40}$/.test(ref)) return
    if (!/^[A-Za-z0-9_./-]+$/.test(ref)) return
    await sh(["config", `branch.${ref}.owner`, sessionID], directory)
    await sh(["config", `branch.${ref}.claimedAt`, String(Math.floor(Date.now() / 1000))], directory)
  } catch {
    // молча: не смогли записать — гейт коммита всё равно проверит по тому, что есть
  }
}

async function branchOwner(directory: string, branch: string): Promise<{ owner: string; fresh: boolean } | null> {
  try {
    const owner = await sh(["config", "--get", `branch.${branch}.owner`], directory)
    if (!owner) return null
    let fresh = true
    try {
      const at = Number(await sh(["config", "--get", `branch.${branch}.claimedAt`], directory))
      if (Number.isFinite(at) && at > 0) {
        fresh = Date.now() / 1000 - at < CLAIM_TTL_SEC
      }
    } catch {
      fresh = true // штампа нет (ручная заявка) — считаем живой
    }
    return { owner, fresh }
  } catch {
    return null // заявки нет — ветка ничья
  }
}

// Свои ветки сессии (для подсказки «куда вернуться»).
async function myBranches(directory: string, sessionID: string): Promise<string[]> {
  try {
    const out = await sh(["config", "--get-regexp", `^branch\\..*\\.owner$`], directory)
    const mine: string[] = []
    for (const line of out.split("\n")) {
      const m = /^branch\.(.+)\.owner\s+(\S+)\s*$/.exec(line)
      if (m && m[2] === sessionID && m[1] !== "main" && m[1] !== "master") {
        mine.push(m[1])
      }
    }
    return mine.slice(0, 5)
  } catch {
    return []
  }
}

async function isDirty(directory: string): Promise<boolean> {
  try {
    const stdout = await new Promise<string>((resolve, reject) => {
      execFile(
        "git",
        ["status", "--porcelain"],
        { cwd: directory },
        (err, out) => (err ? reject(err) : resolve(out)),
      )
    })
    return stdout.trim().length > 0
  } catch {
    return false // fail-open
  }
}

export default Plugin.define({
  id: "tree-hygiene",
  async setup(ctx) {
    const directory = ctx.location.directory

    await ctx.tool.hook("execute.before", async (event: { tool?: string; sessionID?: string; input?: unknown }) => {
      try {
        if (process.env.TREE_HYGIENE === "1") return
        if (event?.tool !== "bash") return

        const cmd = String((event.input as Record<string, unknown>)?.command ?? "")
        const sessionID = String((event as Record<string, unknown>)?.sessionID ?? "")

        if (STASH_RE.test(cmd) && !/-m(\s|=)/.test(cmd) && !/--message/.test(cmd)) {
          throw new Error(
            "TreeHygiene: git stash push требует -m <сообщение> — безымянный stash невозможно разобрать при параллельной работе",
          )
        }

        if (SWITCH_RE.test(cmd) && HAS_REF_RE.test(cmd)) {
          if (await isDirty(directory)) {
            throw new Error(
              "TreeHygiene: грязное дерево — закоммить свой сюжет в task-ветку или уложи в именованный stash ДО смены ветки (TREE_HYGIENE=1 для осознанного обхода)",
            )
          }
          // Чисто: фиксируем владение (реестр виден всем backend'ам и человеку).
          const ref = (HAS_REF_RE.exec(cmd)?.[3] ?? "").trim()
          if (ref) await claimOnSwitch(directory, ref, sessionID)
        }

        // Гейт 3: коммит в чужую живую ветку. main/master — за pre-commit.
        if (COMMIT_RE.test(cmd) && !/CLAIM_OK=1/.test(cmd)) {
          const br = await currentBranchName(directory)
          if (br && br !== "main" && br !== "master") {
            const claim = await branchOwner(directory, br)
            if (claim && claim.fresh && claim.owner !== sessionID) {
              const mine = await myBranches(directory, sessionID)
              const hint = mine.length
                ? `Твои ветки: ${mine.join(", ")}. Вернись: git switch ${mine[0]}.`
                : "Своей заявки не вижу — создай ветку через /branch и работай в ней."
              throw new Error(
                `TreeHygiene: ветка '${br}' заявлена другой живой сессией (владелец ${claim.owner}). ` +
                hint + " Осознанный обход: CLAIM_OK=1 git commit ...",
              )
            }
          }
        }
      } catch (err) {
        if (err instanceof Error && err.message.startsWith("TreeHygiene:")) {
          throw err
        }
        console.error(`[tree-hygiene] guard check failed: ${err}`)
      }
    })
  },
})
