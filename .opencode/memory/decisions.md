---
type: ADR Registry
title: Реестр архитектурных решений — dotfiles
description: ADR для dotfiles. Каждое решение фиксируется здесь.
timestamp: 2026-06-30
---

# Реестр архитектурных решений (ADR) — dotfiles

> Новые ADR добавляются в конец. Формат: ADR-NNN, дата, контекст, решение, альтернативы, последствия.

---

### ADR-001: Инициализация OpenCode в dotfiles
**Дата:** 2026-06-30
**Контекст:** Dotfiles — 23 пакета конфигов, управляемых через GNU Stow. Нужна система для управления, аудита и развития конфигов через ИИ-агентов.
**Решение:**
- 3 primary агента: sysop (инспектор), planner (архитектор), builder (строитель)
- 4 subagent: reviewer, qtile-dev, bash-dev, util-dev
- 8 команд-пайплайнов: /sysaudit, /script, /qtile, /util, /prompt, /notify, /macro, /plugin
- Система памяти: user-profile.md + decisions.md
- Все агенты на DeepSeek v4-flash-free (тестовый период)
**Альтернативы:**
- Один универсальный агент — отвергнуто: нет разделения ролей
- Claude Sonnet для всех — отвергнуто: дорого для тестов
**Последствия:**
- Dotfiles стали управляемым проектом с пайплайнами
- Все агенты read-only или с ограничениями — безопасность
- Масштабируемо: можно добавлять субагентов и пайплайны

### ADR-002: Настройка xdg-desktop-portal для Flameshot
**Дата:** 2026-06-30
**Контекст:** После ребута Flameshot v14 перестал делать скриншоты на X11/Qtile. Ошибка: `org.freedesktop.portal.Desktop` не найден. Диагностика показала:
- `xdg-desktop-portal.service` падает с Dependency failed из-за `Requisite=graphical-session.target`
- `graphical-session.target` имеет `RefuseManualStart=yes` — нельзя запустить вручную
- `XDG_CURRENT_DESKTOP` пустая — portal не может выбрать backend (gtk)
- `dunst` стартует после `flameshot` — notification warning
- Flameshot v14 требует portal даже на X11
**Решение:**
1. Создан systemd override `01-qtile-desktop.conf`: убран `Requisite=` и `After=graphical-session.target` из `xdg-desktop-portal.service`
2. Создан `environment.d/90-desktop.conf` с `XDG_CURRENT_DESKTOP=qtile`
3. Установлен `export XDG_CURRENT_DESKTOP=qtile` в autostart-x11
4. Импортируется env в systemd user session: `systemctl --user import-environment`
5. Перемещён `dunst` перед `flameshot` в порядке запуска
**Альтернативы:**
- Запускать portal напрямую (/usr/lib/xdg-desktop-portal &) — hack, не systemd-way
- Заменить flameshot на maim/scrot — потеря GUI-редактора (стрелки, blur, рамка)
- Создавать wrapper service для graphical-session.target — сложнее, чем override
**Последствия:**
- Portal работает без graphical-session.target (на Qtile он не нужен)
- XDG_CURRENT_DESKTOP=qtile доступен с момента старта user-session
- One-shot после stow: `systemctl --user daemon-reload` + `systemctl --user start xdg-desktop-portal`
- Порядок сервисов логичный: env → portal (dbus-activation) → dunst → flameshot
