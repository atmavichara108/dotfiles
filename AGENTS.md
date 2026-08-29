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

Роутинг задаётся в `opencode.json` через `agent.<name>.model` — модель каждого агента определяет, на чём он считает. Меняя модель, меняешь назначение агента.

| Агент | Роль | Модель (ярус) |
|-------|------|---------------|
| **planner** | проектирует (ADR, спеку), код не пишет; делегирует через `task` | `opencode-go/gpt-5.6-luna` · Strategic |
| **think** | сверх-сложные рассуждения; делегируется planner через `task` | `opencode/grok-build-0.1` · Agentic |
| **builder** | реализует конфиги/скрипты; вызывает `reviewer` | `opencode-go/qwen3.7-plus` · Coding |
| **qtile-dev** | Qtile (WM, виджеты, Python) | `opencode-go/qwen3.7-plus` · Coding |
| **bash-dev** | bash-скрипты, автоматизация | `opencode-go/qwen3.7-plus` · Coding |
| **util-dev** | утилиты (макросы, нотификации, rofi) | `opencode-go/qwen3.7-plus` · Coding |
| **stow-ops** | stow-операции, реструктуризация, миграция, дрейф | `opencode-go/qwen3.7-plus` · Coding |
| **sysop** | `system-audit`: global read-only аудит системы и экосистемы | `opencode-go/deepseek-v4-flash` · Go |
| **reviewer** | read-only quality/style/domain reviewer | `opencode-go/deepseek-v4-flash` · Go |
| **verifier** | верификатор применимости (синтаксис, stow dry-run, готовность) | `opencode/deepseek-v4-flash-free` · Free |
| **researcher** | исследование кода, файлов, git-истории, документации; read-only, предназначен для запуска planner через `task` | `opencode-go/deepseek-v4-flash` · Go |

Canonical global sysop prompt: `opencode-global/.config/opencode/agent/sysop.md`
(после stow — `~/.config/opencode/agent/sysop.md`). Это `system-audit` role:
только sourced read-only audit, без edit/create, commit, `task`/agents,
`system-ops` или system changes. Audit и apply всегда разделены.

Local `.opencode/agent/sysop.md` не удаляется: это dotfiles-specific extension
для Manjaro и действует в local scope с precedence локального определения над
global при его явном выборе. Она не заменяет canonical global role. Live
dispatch/runtime evidence для `/sysaudit` пока не подтверждены.

Точные `model` ID — в `opencode.json` (`agent.<name>.model`), резолвятся из подписок `opencode-go` / `opencode-zen`. Обоснование — ADR-007.

### Конфигурация вызова researcher из planner

Planner (роль: проектирует, НЕ пишет код) имеет конфигурационный контракт для запуска **researcher** без нарушения своей роли. Live dispatch и runtime evidence отдельно не подтверждены.

**Важно:** researcher — subagent, его каноническое определение лежит в global path `opencode-global/.config/opencode/agent/researcher.md` (после stow — `~/.config/opencode/agent/researcher.md`). Для вызова через `task()` необходимо:
1. Агент `researcher` определён в `opencode.json` (`agent.researcher`)
2. Global prompt-файл существует с корректным frontmatter (mode: subagent, permission-блок)
3. Вызывающий агент (planner) имеет `"task": { "*": "allow" }` или `"task": { "researcher": "allow" }`

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

### Кто может вызывать researcher

| Агент | Может вызывать? | Причина |
|-------|----------------|---------|
| **planner** | ✅ `"*": "allow"` | Полный доступ ко всем subagent |
| **builder** | ✅ `"researcher": "allow"` | Добавлено для пайплайнов dev → researcher |
| **qtile-dev** | ❌ | Нет task-permissions |
| **bash-dev** | ❌ | Нет task-permissions |
| **stow-ops** | ❌ | Нет task-permissions |
| **reviewer** | ❌ | Нет task-permissions |
| **verifier** | ❌ | Нет task-permissions |

Canonical reviewer prompt: `opencode-global/.config/opencode/agent/reviewer.md`
(после stow — `~/.config/opencode/agent/reviewer.md`), capability —
`quality-review`. Planner и builder настроены как callers reviewer; live dispatch
и runtime evidence пока не подтверждены. Reviewer возвращает findings,
recommendations и собственный reviewer verdict; acceptance PASS/FAIL остаётся
исключительно за verifier.

## Пайплайны (slash-команды)

`/bridge` · `/sysaudit` · `/script` · `/qtile` · `/util` · `/notify` · `/macro` · `/plugin` · `/stow` · `/loop` · `/prompt` · `/flush`

Глобальная `/spec` читает только canonical execution specs из
`/home/rudra/Projects/OpenCode-Vault/06-Specs/<project>/` после чтения локальных
`AGENTS.md`/`README.md`; локальные pointers не являются источником правды и
недоступность Vault должна давать `BLOCKED`, без fallback.

Большинство: `planner → <dev-agent> → reviewer`. Полные определения — в `.opencode/command/`.
Глобальная `/bridge` запускает protocol entrypoint canonical AndroidOS
Coordination Bridge в текущем репозитории; она не фиксирует агента и не делает
`general` fallback при отсутствии доказуемой named role.

## Конвенции

- Коммиты: `feat(<pkg>): ...`, `fix(<pkg>): ...`, `chore: ...`, `docs: ...` (scope = имя пакета).
- Перед работой читай `.opencode/memory/user-profile.md` (кто такой Макс, стек, предпочтения).
- ADR-реестр: `docs/decisions.md` и `.opencode/memory/decisions.md`.

## Стек (кратко)

Manjaro (X11) · Qtile · zsh + Oh My Zsh + powerlevel10k · Alacritty · Neovim (LazyVim) · tmux · Rofi · Dunst · Picom. Полностью — в `user-profile.md`.
