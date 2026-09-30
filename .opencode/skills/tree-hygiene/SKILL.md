---
name: tree-hygiene
description: Чистое рабочее дерево при параллельной работе в dotfiles — одна task-ветка = один сюжет, до смены ветки/контекста дерево чистое. Использовать при любой git-работе в этом репо.
---

# Tree Hygiene — чистое дерево в dotfiles

Правило закреплено **программно** (не «совестью агентов»):

| Слой | Что принуждает |
|------|----------------|
| `githooks/pre-commit` | branch gate (коммит только в `task/*`; main — merge), conflict-маркеры, **zone-mix** (один коммит = одна зона/сюжет) |
| `plugins/tree-hygiene.ts` | блок `git switch/checkout` при грязном дереве; `git stash push` без `-m` |
| `plugins/main-protector.ts` | блок коммита в main и правки hot-files в main |
| `plugins/branch-auto.ts` | авто-создание `task/<slug>` на старте новой сессии от темы запроса; при грязном дереве — только ref + инструкция; намёк на конфликт — суффикс `-conflict` |
| `/branch` (command) | ручное создание `task/<slug>` от `origin/main` под текущую тему |

## Правила

1. **Старт** — не с `main`: `git switch -c task/<slug>` (от `origin/main`). Автоматика: плагин `branch-auto` создаёт ветку на старте новой сессии; вручную — `/branch`.
2. **Один коммит = один сюжет.** Зоны гейта: `promo-provider | pipboy | opencode | specs-docs | sysconfig | docs | misc`. Смешал зоны в staged → коммит отклонён. Осознанный интеграционный: `MIXED_OK=1 git commit …` — и объясни в сообщении почему.
3. **До смены ветки / конца сессии дерево чистое:** закоммить свой сюжет или `git stash push -m <slug>`. Без `-m` stash плагин не пропустит.
4. **В `main` — только merge** (`ALLOW_MAIN=1` только для осознанного release).
5. **dotfiles — живые stow-симлинки:** НЕ создавай git worktree для этого репо; изоляция = task-ветки в одном checkout.
6. Обходы исключительные и явные: `TREE_HYGIENE=1`, `ALLOW_MAIN=1`, `MIXED_OK=1`, `BRANCH_AUTO=0` — никогда молча.
7. **Финиш `/ship` — новая ветка** (`task/next-<дата>` от обновлённого main),
   не оставаться на `main`. **Намёк на конфликт** (unmerged-пути `UU/AA/DD`,
   `MERGE_HEAD`/`CHERRY_PICK_HEAD`/`REVERT_HEAD`, маркеры `<<<<<<<`) —
   **новая `task/*`-ветка** (с суффиксом `-conflict`, если подсказал плагин),
   разбор только в ней, не в чистой.

## Сюжеты (шпаргалка зон)

- `promo-provider` — `scripts/**`, спеки promo
- `pipboy` — `qtile/`, `rofi/`, спеки pipboy
- `opencode` — `.opencode/`, `opencode-global/`, `opencode.json(c)`, `AGENTS.md`, `githooks/`, `.gitignore`
- `specs-docs` — `docs/specs/`, `docs/decisions.md`
- `sysconfig` — став-пакеты (zsh, nvim, lazygit, proxy, flameshot, …)
- `docs` — остальные `docs/`, README
