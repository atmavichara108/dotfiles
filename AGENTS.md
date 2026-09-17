---
type: Agent Instructions
description: Конвенции, пайплайны и запреты репозитория dotfiles (Manjaro, GNU Stow).
---

# dotfiles — Agent Instructions

Manjaro dotfiles, управляемые через **GNU Stow**. OpenCode здесь — инструмент управления конфигами, не разработка приложения.

**Общение:** отвечай и веди рассуждения на русском — весь репозиторий, документация и агентские конфиги ведутся на русском.

## Модель Stow (самое важное)

- Каждый конфиг — отдельная директория верхнего уровня (`zsh/`, `qtile/`, `nvim/`, …).
- Внутри лежит путь относительно `$HOME`, напр. `qtile/.config/qtile/config.py`.
- `stow <dir>` создаёт симлинки в `$HOME` → правка в пакете сразу «живая».
- Деплой всех пакетов: `./stow.sh` (полный список ≈37 пакетов — внутри скрипта).
- Переставить один пакет: `stow -R <pkg>`.
- Добавить новый пакет: `./add-package.sh <name> <config-path>` (копирует, бэкапит оригинал, стоуит).
- Перед стоуом проверяй конфликты: `stow -n <pkg>` (dry-run).

## Запрещённые действия

Вне scope и/или опасны — **только предлагай, не выполняй**:
- установка/удаление пакетов (`pacman -S/R`, `yay`, `paru`);
- правка `/etc` и системных сервисов (не перезапускай `systemctl` на уровне системы);
- смена прав/владельца (`chmod`, `chown`);
- монтирование ФС.
- **Никаких секретов** (ключи, токены, пароли) в репо — анти-goal, вынесено из репо.

## Роли агентов и роутинг

**Один primary + субагенты.** `sysop` — единственный primary, оператор-оркестратор Manjaro: сам анализирует, проектирует, пишет конфиги и по необходимости запускает субагентов через `task`. Раньше в dotfiles было три primary (sysop/planner/builder) — это плодило путаницу во владении; теперь канон: primary решает, субагенты исполняют.

Канон агента = его `.md`-файл (в `frontmatter`: description/mode/model/permission). Файлы первичны; `opencode.json` не дублирует агентные определения.

| Агент | Тип | Роль | Модель (ярус) |
|-------|-----|------|---------------|
| **sysop** | primary | Оператор-оркестратор Manjaro: планирует, пишет, делегирует субагентам | `opencode-go/gpt-5.6-luna` · Strategic |
| **planner** | subagent | Стратег/ADR: анализирует, проектирует, код не пишет | `opencode-go/gpt-5.6-luna` · Strategic |
| **builder** | subagent | Реализация конфигов/скриптов по спеку | `opencode-go/qwen3.7-plus` · Coding |
| **qtile-dev** | subagent | Qtile (WM, виджеты, Python) | `opencode-go/qwen3.7-plus` · Coding |
| **bash-dev** | subagent | bash-скрипты, автоматизация | `opencode-go/qwen3.7-plus` · Coding |
| **util-dev** | subagent | утилиты (макросы, нотификации, rofi) | `opencode-go/qwen3.7-plus` · Coding |
| **stow-ops** | subagent | stow-операции, реструктуризация, миграция, дрейф | `opencode-go/qwen3.7-plus` · Coding |
| **verifier** | subagent | Верификатор применимости (синтаксис, stow dry-run) — dotfiles-specific | `opencode/deepseek-v4-flash-free` · Free |
| **system-audit** | subagent (global) | read-only аудит системы/экосистемы (ранее глобальный `sysop`) | `opencode-go/glm-5.3-flash` · Go |
| **system-ops** | subagent (global) | approval-gated high-risk apply planning | `opencode-go/gpt-5.6-luna` · Strategic |
| **reviewer** | subagent (global) | read-only quality/style/domain reviewer | `linaliapi/deepseek/deepseek-v4-pro` · Go |
| **researcher** | subagent (global) | исследование кода/файлов/git/документации, read-only | `linaliapi/google/gemini-3.8-flash` · Go |
| **meta** | subagent (global) | правка агентной инфраструктуры OpenCode | `opencode-go/qwen3.7-plus` · Strategic |

Роутинг субагентов задаёт primary `sysop`: `task(agent=…)` под конкретную задачу. Нет задачи из чьей-то зоны → primary делает сам, для несвойственной себе работы не молча отдаёт `general`.

Canonical global system-audit prompt: `opencode-global/.config/opencode/agent/system-audit.md`
(после stow — `~/.config/opencode/agent/system-audit.md`). Только sourced
read-only audit, без edit/create, commit, `task`/agents, `system-ops` или system
changes. Audit и apply всегда разделены.

Canonical global system-ops prompt: `opencode-global/.config/opencode/agent/system-ops.md`
(после stow — `~/.config/opencode/agent/system-ops.md`). Это subagent для
high-risk apply planning: `edit`/`task` deny, dangerous bash deny, а `sudo *`
только `ask`. External read scope ограничен canonical bridge `tasks/**` и
`handoffs/**`; evidence scope остаётся отдельным. Реальный apply возможен лишь
после dry-run/preflight, отдельного явного approval, post-check и rollback plan;
runtime smoke пока не подтверждён.

Local `.opencode/agent/sysop.md` — dotfiles-specific primary (оператор). Глобальный
слой хранит `system-audit.md` (read-only аудит, subagent) — это разные роли: не
путать `sysop` (primary, оркестратор) и `system-audit` (subagent, аудит). Живой
dispatch `/sysaudit` и runtime evidence пока не подтверждены.

Точные `model` ID — в `.md`-frontmatter каждого агента. Обоснование ролей — ADR-001/007; консолидация — ADR-010.

### Конфигурация вызова researcher

Sysop (primary, оркестратор) запускает **researcher** через `task`. Live dispatch и runtime evidence отдельно не подтверждены.

**Важно:** researcher — subagent, его каноническое определение лежит в global path `opencode-global/.config/opencode/agent/researcher.md` (после stow — `~/.config/opencode/agent/researcher.md`). Для вызова через `task()` необходимо:
1. Агент `researcher` определён глобально с корректным `frontmatter` (mode: subagent, permission-блок)
2. Вызывающий primary (sysop) имеет `"task": { "*": "allow" }`

```text
task(
  agent="researcher",
  prompt="Исследуй файлы в qtile/.config/qtile/ и найди все виджеты, 
          которые используют Bar. Верни список файлов и строк."
)
```

Researcher имеет:
- **bash**: read-only (ls, cat, grep, find, git log/diff/show/blame, file, stat, head, tail и т.д.)
- **webfetch**, **websearch** — для поиска документации, API, примеров
- **edit**: deny — никогда не редактирует файлы
- **steps: 30** — достаточно для глубокого исследования

Использовать для:
- Анализа существующих конфигов перед рефакторингом
- Поиска по коду (grep/find)
- Просмотра git-истории и blame
- Поиска документации в интернете
- Быстрой проверки, что уже существует в проекте

## Кто может вызывать субагентов

Запускает субагентов primary **sysop** (`task`). Субагенты между собой не оркестрируют — иерархия плоская: primary → subagent.

| Агент | Вызывает субагентов? | Причина |
|-------|----------------------|---------|
| **sysop** (primary) | ✅ | Единственный оркестратор; `task(agent=…)` по задаче |
| **planner / builder / dev / reviewer / verifier / stow-ops** | ❌ | Субагенты исполняют, не оркестрируют |

Canonical reviewer prompt: `opencode-global/.config/opencode/agent/reviewer.md`
(после stow — `~/.config/opencode/agent/reviewer.md`), capability —
`quality-review`. Sysop настроен как caller reviewer; live dispatch
и runtime evidence пока не подтверждены. Reviewer возвращает findings,
recommendations и собственный reviewer verdict; acceptance PASS/FAIL остаётся
исключительно за verifier.

## Пайплайны (slash-команды)

`/bridge` · `/sysaudit` · `/script` · `/qtile` · `/util` · `/notify` · `/macro` · `/plugin` · `/stow` · `/loop` · `/prompt` · `/flush`

Отдельной slash-команды для `system-ops` нет: маршрут только named task из
`sysop` (primary) после system-audit и с explicit user approval.

Глобальная `/spec` читает только canonical execution specs из
`/home/rudra/Projects/OpenCode-Vault/06-Specs/<project>/` после чтения локальных
`AGENTS.md`/`README.md`; локальные pointers не являются источником правды и
недоступность Vault должна давать `BLOCKED`, без fallback.

Основной: `sysop → <subagent> → verifier`. Для high-risk host scope:
`system-audit → sysop plan → system-ops apply → verifier/post-check`, причём
между plan и apply обязательно explicit user approval. Полные определения — в `.opencode/command/`.
Глобальная `/bridge` запускает protocol entrypoint canonical AndroidOS
Coordination Bridge в текущем репозитории; она не фиксирует агента и не делает
`general` fallback при отсутствии доказуемой named role.

## Конвенции

- Коммиты: `feat(<pkg>): ...`, `fix(<pkg>): ...`, `chore: ...`, `docs: ...` (scope = имя пакета).
- Перед работой читай `.opencode/memory/user-profile.md` (кто такой Макс, стек, предпочтения).
- ADR-реестр: `docs/decisions.md` и `.opencode/memory/decisions.md`.

## Стек (кратко)

Manjaro (X11) · Qtile · zsh + Oh My Zsh + powerlevel10k · Alacritty · Neovim (LazyVim) · tmux · Rofi · Dunst · Picom. Полностью — в `user-profile.md`.
