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
| **planner** | проектирует (ADR, спеку), код не пишет; делегирует через `task` | Haiku · Reasoning |
| **builder** | реализует конфиги/скрипты; вызывает `reviewer` | Qwen · Coding |
| **qtile-dev** | Qtile (WM, виджеты, Python) | Qwen · Coding |
| **bash-dev** | bash-скрипты, автоматизация | Qwen · Coding |
| **util-dev** | утилиты (макросы, нотификации, rofi) | Qwen · Coding |
| **stow-ops** | stow-операции, реструктуризация, миграция, дрейф | Qwen · Coding |
| **sysop** | read-only аудит системы | DeepSeek · Light |
| **reviewer** | ревьюер (PASS/FAIL, безопасность, спека) | DeepSeek · Light |
| **verifier** | верификатор применимости (синтаксис, stow dry-run, готовность) | DeepSeek · Light |

Точные `model` ID — в `opencode.json` (`agent.<name>.model`), резолвятся из подписок `opencode-go` / `opencode-zen`. Обоснование — ADR-007.

## Пайплайны (slash-команды)

`/sysaudit` · `/script` · `/qtile` · `/util` · `/notify` · `/macro` · `/plugin` · `/stow` · `/loop` · `/prompt` · `/flush`

Большинство: `planner → <dev-agent> → reviewer`. Полные определения — в `.opencode/command/`.

## Конвенции

- Коммиты: `feat(<pkg>): ...`, `fix(<pkg>): ...`, `chore: ...`, `docs: ...` (scope = имя пакета).
- Перед работой читай `.opencode/memory/user-profile.md` (кто такой Макс, стек, предпочтения).
- ADR-реестр: `docs/decisions.md` и `.opencode/memory/decisions.md`.

## Стек (кратко)

Manjaro (X11) · Qtile · zsh + Oh My Zsh + powerlevel10k · Alacritty · Neovim (LazyVim) · tmux · Rofi · Dunst · Picom. Полностью — в `user-profile.md`.
