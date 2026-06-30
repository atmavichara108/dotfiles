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
- `xdg-desktop-portal.service` падает с Dependency failed
- `XDG_CURRENT_DESKTOP` пустая — portal не может выбрать backend (gtk)
- `dunst` стартует после `flameshot` — notification warning
- Flameshot v14 требует portal даже на X11
**Решение:**
1. Установить `export XDG_CURRENT_DESKTOP=qtile` в autostart-x11
2. Импортировать переменную в systemd user session: `systemctl --user import-environment`
3. Активировать `graphical-session.target` и portal-сервисы при старте
4. Переместить `dunst` перед `flameshot` в порядке запуска
5. Добавить `sleep 0.5` перед flameshot для гарантии готовности сервисов
**Альтернативы:**
- Удалить portal и использовать X11 fallback — flameshot v14 всё равно требует portal
- Заменить flameshot на maim/scrot — потеря GUI-редактора (стрелки, blur, рамка)
- Не лечить portal, а патчить flameshot — нет гарантии что сработает
**Последствия:**
- Portal работает корректно для всех portal-зависимых приложений
- Порядок сервисов стал логичным: env → portal → dunst → flameshot
- Одноразово нужно импортировать env в systemd (делается в autostart)
