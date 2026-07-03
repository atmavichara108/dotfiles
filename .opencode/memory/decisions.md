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
- 5 subagent: reviewer, verifier, qtile-dev, bash-dev, util-dev
- 10 команд-пайплайнов: /sysaudit, /script, /qtile, /util, /prompt, /notify, /macro, /plugin, /loop, /flush

---

### ADR-010: Verifier + closed-loop + flush протокол
**Дата:** 2026-07-03
**Контекст:** Нужна превентивная проверка применимости (а не только стиля) перед apply изменений dotfiles, и автономный цикл build→verify→fix. Отдельно — формализация pre-compaction flush, чтобы контекст сессии не терялся при компакции.
**Решение:**
- Новый subagent `verifier` — PASS/FAIL применимости: синтаксис (bash -n / py_compile / zsh -n / shellcheck), `stow -n` dry-run, разрешение зависимостей (which), идемпотентность. edit: deny, bash — read-only whitelist. Отличие от reviewer: reviewer=стиль/безопасность/спека, verifier=готовность к apply.
- Команда `/loop` (builder, subtask) — closed-loop build→verify→fix, HARD STOP после 5 циклов, verifier единственный источник PASS/FAIL.
- Команда `/flush` (planner) — ручной pre-compaction flush: дописать ADR/согласованные правки в `decisions.md` (append-only, дедуп).
**Альтернативы:**
- Один reviewer на всё — отвергнуто: смешение стиля и применимости, дольше и менее точно.
- Авто- flush на каждом шаге — отвергнуто: дорого по токенам, только контрольные точки.
**Последствия:**
- 5 subagent (было 4), 10 команд (было 8).
- Verifier = референс для verifier-pattern в других проектах.
- Flush-протокол формализован в `vault/02-Methods/memory-management.md`, внедрён в dotfiles ✅.
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
- Реальная причина: Qt 6.11 + NVIDIA regression, не portal
**Решение:**
1. Создан полный override unit `systemd/.../xdg-desktop-portal.service`: убран `Requisite=` и `After=graphical-session.target` (drop-in не работает на systemd 260 — не сбрасывает list-директивы)
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
- Вместо drop-in используется полный override unit (systemd 260 не сбрасывает Requisite= через пустое значение)
- Порядок сервисов логичный: env → portal (dbus-activation) → dunst → flameshot

**Резолюция (2026-06-30):** Portal-fixes оказались ложным следом. 
Реальная причина: регрессия Flameshot v14 + Qt 6.11 + NVIDIA на X11 — 
`QScreen::grabWindow()` зависает в XCB/NVIDIA. Решение: даунгрейд 
до `flameshot-imgur` (v13.3.0) — работает стабильно, тот же бинарник 
`/usr/bin/flameshot`, все фичи сохранены.

---

## 2026-07-01 — Очистка артефактов + ADR-003

### Удалено
- `scripts/.local/bin/aider` — старый артефакт, внешний symlink на uv-установленный aider-chat. Удалён из репо.

### Зафиксировано
- **ADR-003** — tmux: гибридное управление плагинами (tpm как submodule, остальные — full clone). docs/decisions.md.
- **Вывод секретов из репо** — GITHUB_TOKEN был артефактом в zsh/.zshrc, удалён. Осознанная практика: секреты — в игнорируемые файлы (.zshrc.local / .env).
- **Chrome → Chromium** — смена браузера по умолчанию в mimeapps.list.
- **Включён LSP** в opencode.json.
- **git pull.rebase = true** — rebase по умолчанию.
- **Добавлены хуки:** nvm, bun, direnv в zsh/.zshrc.

### ADR-002: Система «на потом» (Deferred Registry)
**Дата:** 2026-06-30
**Контекст:** Макс часто говорит «запиши на потом», «отложи», «someday». Без системы эти задачи теряются.
**Решение:**
- Создан `docs/deferred.md` — реестр отложенных задач с контекстом, причиной и триггером возврата
- Создана команда `/someday` для добавления записей
- Макс подтвердил: «то что я говорю на потом, ты всегда должен документировать чтобы иметь список на потом»
- Добавлена мета-инструкция: planner НЕ выполняет destructive-операции, делегирует subagent-ам
**Альтернативы:**
- todo.txt в корне — отвергнуто: нет структуры и триггеров возврата
- GitHub Issues — отвергнуто: не terminal-native
**Последствия:**
- Все deferred-задачи теперь не теряются
- При каждом аудите реестр пересматривается
- `/someday` доступен всем агентам

### ADR-003: Planner — read-only, делегирование subagent-ам
**Дата:** 2026-06-30
**Контекст:** Planner пытался выполнить stow --adopt и git commit напрямую, но права запрещают destructive-операции. Макс указал: «если нужно выполнить задачи выходящие за твои компетенции планера, вызывай суб агентов».
**Решение:**
- Planner — строго read-only: аудит, проектирование, документирование
- Для stow, git, файловых операций — вызывать subagent (general, builder)
- Записано в deferred.md как постоянная инструкция
**Последствия:**
- Чистое разделение ответственности
- Безопасность — destructive-операции только с разрешения пользователя
- Масштабируемость — любая задача декомпозируется на read-only (planner) + mutation (subagent)
