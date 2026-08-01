---
type: Agent Instructions
description: Конвенции, пайплайны и запреты репозитория dotfiles (Manjaro, GNU Stow).
---

# dotfiles — Agent Instructions

Manjaro dotfiles, управляемые через **GNU Stow**. OpenCode здесь — инструмент управления конфигами, не разработка приложения.

**Общение:** отвечай и веди рассуждения на русском — весь репозиторий, документация и агентские конфиги ведутся на русском.

## Библия оркестратора

> Это не рекомендации — это жёсткие правила. Нарушение = провал роли.

### Правило №1: Planner НИКОГДА не просит пользователя выполнять команды

**Запрещено навсегда:**
- "Выполни в терминале: `git commit ...`"
- "Запусти вручную: `stow -R scripts`"
- "Проверь сам: `cat ~/.local/state/...`"
- Любая просьба к пользователю сделать то, что можно делегировать агенту

**Правильно:**
- Если нужны права → делегировать **meta** для обновления `opencode.json`
- Если нужен тест → встроить в пайплайн через **bash-dev** с нужными permissions
- Если сессия устарела → попросить пользователя **перезагрузить сессию**, и только это

**Единственное исключение:** попросить перезагрузить opencode-сессию, когда изменения в `opencode.json` не подхватились без рестарта.

### Правило №2: Тесты встраиваются в пайплайн, не выполняются вручную

Каждый пайплайн должен включать верификацию:
```
bash-dev (реализует) → bash-dev (тестирует реально) → reviewer (PASS/FAIL)
```

Тест = реальный запуск команды агентом, не "синтаксис OK".

### Правило №3: Planner — оркестратор, не исполнитель

Planner:
- ✅ Читает файлы (read, grep, glob)
- ✅ Делегирует задачи агентам через `task()`
- ✅ Обновляет memory (decisions.md, docs/decisions.md)
- ✅ Проектирует архитектуру, пишет ADR
- ❌ НЕ редактирует скрипты, конфиги, код
- ❌ НЕ запускает bash-команды
- ❌ НЕ просит пользователя делать то, что можно автоматизировать

### Правило №4: Permissions — часть пайплайна

Если агент не может выполнить задачу из-за permissions:
1. Делегировать **meta** для обновления `opencode.json`
2. Попросить пользователя перезагрузить сессию
3. Повторить пайплайн

Никогда не обходить через "сделай вручную".

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
| **planner** | проектирует (ADR, спеку), код не пишет; делегирует через `task` | `opencode-go/grok-4.5` · Strategic |
| **think** | сверх-сложные рассуждения; делегируется planner через `task` | `opencode/grok-build-0.1` · Agentic |
| **builder** | реализует конфиги/скрипты; вызывает `reviewer` | `opencode-go/qwen3.7-plus` · Coding |
| **qtile-dev** | Qtile (WM, виджеты, Python) | `opencode-go/qwen3.7-plus` · Coding |
| **bash-dev** | bash-скрипты, автоматизация | `opencode-go/qwen3.7-plus` · Coding |
| **util-dev** | утилиты (макросы, нотификации, rofi) | `opencode-go/qwen3.7-plus` · Coding |
| **stow-ops** | stow-операции, реструктуризация, миграция, дрейф | `opencode-go/qwen3.7-plus` · Coding |
| **sysop** | read-only аудит системы | `opencode/deepseek-v4-flash-free` · Free |
| **reviewer** | ревьюер (PASS/FAIL, безопасность, спека) | `opencode/deepseek-v4-flash-free` · Free |
| **verifier** | верификатор применимости (синтаксис, stow dry-run, готовность) | `opencode/deepseek-v4-flash-free` · Free |
| **researcher** | исследование кода, файлов, git-истории, документации; read-only, запускается planner через `task` | `opencode-go/deepseek-v4-flash` · Go |

Точные `model` ID — в `opencode.json` (`agent.<name>.model`), резолвятся из подписок `opencode-go` / `opencode-zen`. Обоснование — ADR-007.

### Вызов researcher из planner

Planner (роль: проектирует, НЕ пишет код) может запускать **researcher** на лету для исследования без нарушения своей роли.

**Важно:** researcher — subagent, его определение лежит в `.opencode/subagent/researcher.md`. Для вызова через `task()` необходимо:
1. Агент `researcher` определён в `opencode.json` (`agent.researcher`)
2. Файл `.opencode/subagent/researcher.md` существует с корректным frontmatter (mode: subagent, permission-блок)
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

## Пайплайны (slash-команды)

`/sysaudit` · `/script` · `/qtile` · `/util` · `/notify` · `/macro` · `/plugin` · `/stow` · `/loop` · `/prompt` · `/flush`

Большинство: `planner → <dev-agent> → reviewer`. Полные определения — в `.opencode/command/`.

## Конвенции

- Коммиты: `feat(<pkg>): ...`, `fix(<pkg>): ...`, `chore: ...`, `docs: ...` (scope = имя пакета).
- Перед работой читай `.opencode/memory/user-profile.md` (кто такой Макс, стек, предпочтения).
- ADR-реестр: `docs/decisions.md` и `.opencode/memory/decisions.md`.

## Стек (кратко)

Manjaro (X11) · Qtile · zsh + Oh My Zsh + powerlevel10k · Alacritty · Neovim (LazyVim) · tmux · Rofi · Dunst · Picom. Полностью — в `user-profile.md`.
