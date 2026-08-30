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

---

### ADR-004: Субагент stow-ops + команда /stow
**Дата:** 2026-07-10
**Контекст:** При аудите dotfiles обнаружен массовый дрейф симлинков, 9 приложений не под stow, мусор в scripts/.local/bin/. Builder не мог выполнить массовые файловые операции (mkdir, cp, mv, stow) — не было подходящего субагента с нужными правами. Существующие subagent (bash-dev, qtile-dev, util-dev) специализированы на содержимом конфигов, не на файловых операциях.
**Решение:**
- Создан subagent `stow-ops` (mode: subagent) — специалист по файловым операциям:
  - Права: mkdir, cp, mv, ln, stow*, chmod +x, touch, ls, cat, grep, find, git diff/status
  - Запрещено: rm, sudo, pacman, systemctl, yay, paru
  - Задача: массовые stow-операции, исправление дрейфа, реструктуризация пакетов, миграция конфигов, обновление stow.sh/.gitignore
- Создана команда `/stow` (agent: builder, subtask): пайплайн builder (планирование) → stow-ops (выполнение) → verifier (верификация)
- HARD STOP после 3 verify-циклов
- Builder обновлён: добавлен `stow-ops: allow` в task permissions
**Альтернативы:**
- general-агент для всех файловых операций — отвергнуто: нет специализации, идемпотентности, проверок
- Расширить права builder — отвергнуто: builder уже имеет много ответственности
- Использовать bash-dev — отвергнуто: bash-dev не имеет прав на cp, mv, stow (полный)
**Последствия:**
- 6 subagent (было 5), 11 команд (было 10)
- Чёткое разделение: builder = содержимое конфигов, stow-ops = файловые операции
- Verifier — обязательный шаг после stow-ops (dry-run stow -n, проверка симлинков)

---

### ADR-005: Пакет opencode-global в dotfiles
**Дата:** 2026-07-10
**Контекст:** Глобальный конфиг OpenCode (~/.config/opencode/) содержал ценные компоненты: meta-агент (@meta), глобальный verifier (с моделью glm-5.2, отличной от проектного deepseek-v4), команды done/loop, плагин session-flush.ts. Все эти файлы не были под версионированием и могли быть потеряны при переустановке системы.
**Решение:**
- Создан stow-пакет `opencode-global/.config/opencode/` в dotfiles
- Версионируются: agent/meta.md, agent/verifier.md, command/done.md, command/loop.md, plugins/session-flush.ts, opencode.jsonc, package.json, .gitignore, AGENTS.md
- Исключены (в .gitignore): node_modules/, package-lock.json, bun.lock
- При stow старый ~/.config/opencode бэкапится, новый становится симлинком
- Зависимости (opencode-ai/plugin) восстанавливаются через npm install в целевой директории
**Альтернативы:**
- Не версионировать — отвергнуто: потеря глобальных агентов при переустановке
- Версионировать в отдельном репо — отвергнуто: избыточно, все dotfiles в одном месте
**Последствия:**
- 36 пакетов в dotfiles (было 35)
- При клоне dotfiles на новую систему: npm install в ~/.config/opencode для восстановления плагина
- meta-агент и глобальный verifier переносимы между проектами

---

### ADR-006: Аудит и реструктуризация dotfiles (2026-07-10)
**Дата:** 2026-07-10
**Контекст:** Sysop-аудит выявил системные проблемы:
1. Дрейф симлинков: gtk-4.0/gtk.css (реальный файл, не симлинк), wal/templates/ (3 из 4 файлов реальные), nvim/.neoconf.json (реальный)
2. 9 приложений в ~/.config/ не под stow: flameshot, wallust, copyq, thefuck, tinted-theming, nitrogen, calcurse, proxyctl, task-tools (объединяет taskwarrior-tui, taskvanguard, timewarrior)
3. scripts/.local/bin/ замусорен 28 pipx-артефактами (симлинки на venv faster-whisper, syncall) + бинарём pm3 (13MB)
4. stow.sh устарел — массив packages содержал только 6 пакетов (из них fzf не существовал)
5. .gitignore не содержал runtime-исключений для новых пакетов
**Решение:**
- Исправлен дрейф: gtk-4.0, wal/templates, nvim → все файлы симлинки
- Созданы 9 новых пакетов: flameshot, wallust, copyq, thefuck, tinted-theming, task-tools, nitrogen, calcurse, proxyctl
- Создан объединённый пакет task-tools (taskwarrior-tui + taskvanguard + timewarrior)
- Очищен scripts/.local/bin: 28 pipx-артефактов перемещены в /tmp/opencode/
- Обновлён stow.sh: 36 пакетов в массиве, убран несуществующий fzf
- Обновлён .gitignore: +29 строк runtime-исключений для новых пакетов
- Верификация: 6/6 критериев PASS (строк 14 пакетов без конфликтов)
**Альтернативы:**
- Постепенная миграция — отвергнуто: дрейф накапливается, проще сделать одномоментно
- Не объединять task-пакеты — отвергнуто: 3 пакета с 1 файлом каждый — избыточно
**Последствия:**
- 36 пакетов под stow (было 23)
- Все симлинки централизованы, дрейф устранён
- scripts/.local/bin содержит только 10 легитимных скриптов
- Пайплайн для будущих миграций: planner (аудит) → stow-ops (выполнение) → verifier (верификация)

---

### ADR-007: Researcher — read-only subagent для исследовательских задач
**Дата:** 2026-07-21
**Контекст:** Planner (read-only) нуждается в возможности запускать исследовательские задачи (grep, find, git log, webfetch, websearch) не нарушая свою роль. Раньше researcher.md лежал в `.opencode/agents/`, а должен быть в `.opencode/subagent/` — из-за этого `task(agent="researcher"...)` возвращал "Unknown agent type".
**Решение:**
- `researcher` — subagent с mode: subagent, edit: deny, read-only bash + webfetch + websearch
- Определение: `opencode.json` → `agent.researcher`, инструкции: `.opencode/subagent/researcher.md`
- Файл перемещён из `.opencode/agents/researcher.md` в `.opencode/subagent/researcher.md`
- Planner: `"task": { "*": "allow" }` — может вызывать researcher (и любых других subagent)
- Builder: добавлен `"researcher": "allow"` в task permissions для использования в пайплайнах
- Frontmatter researcher.md приведён к единому стандарту (permission-блок как у других subagent)
**Альтернативы:**
- Дать planner прямые read-only bash права — отвергнуто: смешение ролей, planner проектирует а не исследует
- Создать отдельного агента explore — отвергнуто: researcher покрывает все read-only сценарии
**Последствия:**
- Planner теперь может делегировать исследование researcher через `task(agent="researcher", prompt="...")`
- Builder также может вызывать researcher в пайплайнах (например, `/research` команда)
- Явная таблица кто может вызывать researcher в AGENTS.md

---

### ADR-008: Chromium запускается через единый HAPP-aware wrapper
**Дата:** 2026-08-29
**Контекст:** HAPP на `127.0.0.1:10808`/`10809` подтверждён через `curl`, а
Chromium с явным proxy flag и чистым профилем работает. Системный desktop entry
запускает Chromium напрямую; singleton-процесс не принимает proxy flag второго
запуска.
**Решение:** Обычный Chromium запускается через stow-wrapper с учётом
`proxyctl`; пользовательский desktop entry и обычные launch-paths используют
wrapper. `Super+G` запускает обычный Chromium, `Super+Shift+G` для Genspark/Tor
сохраняется. Tor web-apps и TUN не меняются.
**Альтернативы:** env-переменные и ручной flag отвергнуты из-за отсутствия
надёжной автоматизации; TUN отвергнут по ADR-004.
**Последствия:** Единый proxy entrypoint Chromium; после смены proxy mode нужен
полный выход Chromium. Реализация выполняется по спецификации Chromium/HAPP.

---

### Flush 2026-08-29: Состояние реализации Chromium/HAPP
**Контекст:** В ходе реализации первоначальный wrapper оказался жёстко привязан
к HTTP-порту 10809 и был неисполняемым; reviewer/verifier это выявили.
**Решение:** Builder довёл реализацию до требований ADR-008: wrapper исполняемый,
читает `proxyctl/mode`, поддерживает `happ`/`tor`/`off`/`auto`; Ranger не обходит
wrapper; пользовательский desktop entry и `Super+G` направлены через него.
Случайное изменение `environment.d/proxy.conf` откатено.
**Последствия:** Автоматические проверки (bash, desktop entry, Python, Stow и
режимы wrapper) заявлены PASS. Ручная проверка launch-paths и утечки
маршрута остаётся перед production-применением. Коммит и push на момент flush
не выполнялись.

---

### Flush 2026-08-30: T-108 — permission/root smoke-test
**Контекст:** В canonical AndroidOS Coordination Bridge добавлены task
`AOS-T108-001` и handoff `H-108-002` для проверки dotfiles-local
`system-ops`. Требовалось исключить root/host mutation и сохранить новый
append-only evidence непосредственно в bridge.
**Решение:** Маршрут зафиксирован как named `system-ops`; разрешены только
read-only audit и запись нового файла в
`/home/rudra/Projects/AndroidOS/coordination/bridge/evidence/**`. В
`opencode.json` сохранены deny для task и опасных операций, `sudo *: ask`, а
доступ к task/handoff/evidence ограничен canonical bridge scopes.
**Наблюдение:** Fresh named dispatch доказал чтение task/handoff и корректную
статическую policy, но runtime заблокировал `apply_patch` при записи
`E-108-003.md`. Host, dotfiles WIP, task, handoff и старое evidence не менялись.
`E-108-002.md` создан librarian как partial report и не является evidence,
созданным `system-ops`.
**Статус:** T-108 остаётся `BLOCKED`: persistence gate не пройден. Не доказано,
что причина — stale session; текущий gap — несоответствие между effective
`edit` allow для внешнего evidence path и фактическим permission evaluator
`apply_patch`.
**Следствие:** Не расширять allowlist и не использовать fallback. Нужен
отдельный runtime-level способ дать named `system-ops` запись только в
`evidence/**`; после этого создать новый `E-108-003.md` append-only и передать
его librarian. Коммит и push не выполнялись.
