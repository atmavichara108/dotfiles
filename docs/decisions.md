# Архитектурные решения (ADR) — dotfiles

> Реестр ADR. Новые решения добавляются в конец.

---

### ADR-001: Инициализация OpenCode в dotfiles
**Дата:** 2026-06-30
**Контекст:** Dotfiles — 23 пакета конфигов, управляемых через GNU Stow.
**Решение:**
- 3 primary агента: sysop, planner, builder
- 4 subagent: reviewer, qtile-dev, bash-dev, util-dev
- 8 команд-пайплайнов
**Альтернативы:** Один универсальный агент — отвергнуто.
**Последствия:** Dotfiles — управляемый проект с пайплайнами.

---

### ADR-002: Настройка xdg-desktop-portal для Flameshot
**Дата:** 2026-06-30
**Контекст:** После ребута Flameshot v14 перестал делать скриншоты на X11/Qtile. Ошибка: `org.freedesktop.portal.Desktop` не найден.
**Решение:**
1. Systemd override для xdg-desktop-portal: убран Requisite=graphical-session.target
2. environment.d/90-desktop.conf с XDG_CURRENT_DESKTOP=qtile
3. export + import-environment в autostart-x11
4. Перемещён dunst перед flameshot
**Альтернативы:**
- Запускать portal напрямую (/usr/lib/xdg-desktop-portal &) — не systemd-way
- Заменить flameshot на maim/scrot — потеря GUI-редактора
- Wrapper для graphical-session.target — сложнее override
**Последствия:** Portal работает без graphical-session.target (Requisite= удалён). One-shot: daemon-reload. Порядок сервисов: env → portal → dunst → flameshot.
