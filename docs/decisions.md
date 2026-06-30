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
1. Установить `export XDG_CURRENT_DESKTOP=qtile` в autostart-x11
2. Импортировать переменную в systemd user session
3. Активировать `graphical-session.target` и portal-сервисы при старте
4. Переместить `dunst` перед `flameshot` в порядке запуска
5. Добавить `sleep 0.5` перед flameshot
**Альтернативы:**
- Удалить portal — flameshot v14 всё равно требует portal
- Заменить flameshot на maim/scrot — потеря GUI-редактора
**Последствия:** Portal работает корректно, порядок сервисов логичный.
