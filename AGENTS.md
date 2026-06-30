---
type: Agent Instructions
title: dotfiles — правила и архитектура
description: Конвенции, пайплайны, агенты, UX-профиль dotfiles.
timestamp: 2026-06-30
---

# dotfiles — Agent Instructions

> Manjaro dotfiles, управляемые через GNU Stow. OpenCode здесь = операционная система для управления конфигами, не разработка кода.

## UX-профиль

Ты работаешь для **Макса** — вайбкодера, системного инженера.
Полный профиль: `.opencode/memory/user-profile.md`

**Кратко:** минимализм, автоматизация, эстетика, производительность, модульность.
Русский язык, терминал-нативный стек, тёмная тема, консистентность цветов.

## Архитектура агентов

### Primary агенты
| Агент | Роль | Модель |
|-------|------|--------|
| **sysop** | Инспектор системы (read-only аудит) | deepseek-v4-flash-free |
| **planner** | Архитектор (ADR, планы, дизайн) | deepseek-v4-flash-free |
| **builder** | Строитель (конфиги, скрипты, модули) | deepseek-v4-flash-free |

### Subagent
| Агент | Роль | Модель |
|-------|------|--------|
| **reviewer** | Ревьюер (PASS/FAIL, безопасность) | deepseek-v4-flash-free |
| **qtile-dev** | Qtile-специалист (WM, виджеты, Python) | deepseek-v4-flash-free |
| **bash-dev** | Bash-специалист (скрипты, автоматизация) | deepseek-v4-flash-free |
| **util-dev** | Утилиты (макросы, нотификации, rofi) | deepseek-v4-flash-free |

## Пайплайны (команды)

| Команда | Пайплайн | Назначение |
|---------|----------|-----------|
| `/sysaudit` | sysop | Аудит системы: пакеты, конфиги, дрейф, сервисы |
| `/script` | planner → bash-dev → reviewer | Создание/изменение bash-скриптов |
| `/qtile` | planner → qtile-dev → reviewer | Разработка qtile: конфиги, виджеты, хуки |
| `/util` | planner → util-dev → reviewer | Создание утилит: btop-темы, wal-схемы |
| `/prompt` | builder → docs/cheatsheets/ | Создание чит-шитов и подсказок |
| `/notify` | util-dev → reviewer | Настройка уведомлений (dunst) |
| `/macro` | util-dev → reviewer | Макросы: sxhkd, rofi-меню, горячие клавиши |
| `/plugin` | builder → reviewer | Плагины для nvim, rofi, btop и др. |

## Конвенции

- **Менеджер:** GNU Stow. Каждый конфиг — отдельная директория.
- **Структура:** `директория/.файл` → `stow директория` → симлинк в `$HOME`.
- **Коммиты:** `feat(shell): ...`, `fix(nvim): ...`, `chore: ...`, `docs: ...`
- **Никаких секретов:** ключи, токены, пароли — НЕ в репо.

## Запрещённые действия

- **НЕ** ставь/удаляй пакеты (`pacman -S`, `yay`, `paru`) — только предлагай команды.
- **НЕ** правь `/etc` — только предлагай изменения.
- **НЕ** меняй права (`chmod`, `chown`) — только предлагай.
- **НЕ** перезапускай сервисы — только предлагай.
- **НЕ** монтируй/размонтируй файловые системы.

## Архитектура (кратко)

```
dotfiles/
├── opencode.json          ← конфиг OpenCode, все агенты
├── AGENTS.md              ← этот файл
├── docs/
│   ├── decisions.md       ← ADR
│   ├── user-profile.md    ← UX-профиль (краткий)
│   └── cheatsheets/       ← шпаргалки
├── .opencode/
│   ├── agent/             ← primary агенты
│   ├── subagent/          ← subagent
│   ├── command/           ← пайплайны
│   └── memory/            ← память (user-profile, decisions)
├── zsh/ nvim/ tmux/ git/  ← пакеты Stow (23 штуки)
├── stow.sh                ← массовый stow
└── add-package.sh         ← новый пакет
```

## Память

- `.opencode/memory/user-profile.md` — кто Макс, как работает, предпочтения
- `.opencode/memory/decisions.md` — реестр ADR
- `docs/cheatsheets/` — шпаргалки для пользователя

Все агенты читают user-profile.md перед работой.

## Окружение

- **OS:** Manjaro (Arch-based)
- **Shell:** zsh + powerlevel10k
- **WM:** Qtile (X11)
- **Terminal:** Alacritty
- **Editor:** Neovim
- **Launcher:** Rofi
- **Notifications:** Dunst
