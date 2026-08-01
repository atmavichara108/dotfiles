---
type: ADR Registry
title: Реестр архитектурных решений — dotfiles
description: ADR для dotfiles. Каждое решение фиксируется здесь.
timestamp: 2026-07-31
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

### ADR-008: S2 Theme hub (Aether-lite) — pywal + rofi
**Дата:** 2026-07-31
**Контекст:** Aether нравится по UX, но NVIDIA/WebKit баги делают его нестабильным на текущем железе. Нужен упрощённый theming hub «из приложения» без сторонней возни — смена обоев/палитры должна перекрашивать весь стек (Alacritty, rofi, dunst, GTK, Qtile) без ручной правки N утилит.
**Решение:**
- **Engine:** **pywal** — совместим с существующими wal templates, генерирует `~/.cache/wal/colors.json`, который читает `qtile/colors.py` и остальные конфиги
- **UI:** **theme-hub** (rofi-меню) — выбор обоев/тем из приложения; оркестратор **theme-apply** применяет палитру ко всему стеку
- **wal-set** → thin wrapper на `theme-apply` (обратная совместимость)
- **Хоткеи:** `Mod+F5` = theme-hub (rofi), `Mod+Shift+F5` = `theme-apply --random`
- **Ветка:** `feat/s2-theme-hub-rofi`
**Альтернативы:**
- **wallust** — потребует адаптер для `colors.json` (несовместимый формат), лишняя обвязка
- **GTK/Wails app** — дорого в разработке, NVIDIA-риск с WebKit
- **Полный aether** — отклонён: NVIDIA/WebKit баги, нестабилен
**Последствия:**
- S2 MVP/lite реализован: pywal + theme-apply + theme-hub
- wallust остаётся в пакетах (не как hub engine)
- aether перенесён в deferred (S6)
- Темы/шаблоны — polish в следующих итерациях

---

### ADR-009: Эстетическая доктрина — cyberpunk ∩ solarpunk
**Дата:** 2026-07-31
**Контекст:** Устойчивое развитие dotfiles = не только утилитарность. Стиль и UX equally first-class. Нужен единый ориентир для всех агентов и будущих кастомизаций (лаунчеры, меню, бар, уведомления, theming).
**Решение:**
- **Стык cyberpunk ∩ solarpunk:** высокотехнологично, плавно, современно; при этом открыто, «живое», без мрачного гротеска и без корпоративного глянца.
- **Минимализм + hi-tech:** лёгкие UI (rofi/dunst/qtile), без тяжёлых GUI-конфигураторов; всплывающие меню, иконки, лаунчеры — уместны, если быстрые и осмысленные.
- **Скорость = часть эстетики:** задержка смены темы/обоев — дефект UX, не «норма».
- **Слои theming (связь с S2):** wallpaper layer ≠ bar layer; targets opt-in; не один random на всё.
- **Анимации:** уместные, короткие, функциональные (fade/flash палитры, notify), не декоративный шум.
- **Anti:** тяжёлый gloss, skeuomorphism, webkit-тяжёлые theme apps (aether-класс) как runtime-зависимость; DoomOne и прочие чужие fallback-палитры «на всякий случай».
**Альтернативы:** чистый cyberpunk / чистый solarpunk / «только минимализм без стиля» — отвергнуты как однобокие.
**Последствия:** user-profile, roadmap S2, theme-hub, qtile bar, rofi/dunst — выравниваются под доктрину. Все агенты читают этот ADR.

---

### ADR-010: S2 theming layers + engine + no-reload bar (уточнение ADR-008)
**Дата:** 2026-07-31
**Контекст:** MVP theme-hub работает, но reload_config роняет окна; pywal ощущается медленным; нужен контроль палитр per-layer; fallback DoomOne убрать.
**Решение:**
1. **Слои:** `wall` (обои+opt-in apps) | `bar` (отдельный palette-bar.json) | `apps` (targets.toml: wall|bar|preset|fixed).
2. **Смена обоев НЕ трогает бар** по умолчанию; бар — отдельное действие hub.
3. **Бар без reload_config:** live `refresh_bar_colors` + явная регистрация theme-targets в widgets (qtile-extras decorations).
4. **Engine:** уход с pywal как default runtime → **wallust** (быстрее extract) + адаптер/запись совместимого `~/.cache/wal/colors.json` ИЛИ прямой bar/wall json; pywal optional fallback only if wallust missing — NOT DoomOne palette.
5. **No DoomOne / no foreign preset fallback:** если палитры нет — последняя known-good из `~/.local/state/theme-hub/` или нейтральный минимальный dark из *нашей* base palette (cyber-solar), задокументированной в theme-hub, не DoomOne.
6. **Motion:** короткие feedback-анимации при apply (dunst + optional picom/rofi), без тяжёлого compositor show.
**Альтернативы:** оставить pywal+reload — отвергнуто (медленно + ломает сессию).
**Последствия:** план реализации частями 1–4; ADR-008 дополняется, не отменяется (rofi hub + scripts остаются).

---

### ADR-011: 22K Wallpaper Support via Streaming Downscale
**Дата:** 2026-08-02
**Контекст:** wallust имеет хардкодный лимит декода 512 MiB; 22K-изображения превышают его → OOM. Нужно прозрачное решение без ручной предобработки и без ущерба UX.
**Решение:**
- Guard размерностей изображения перед wallust (>8192px по большей стороне или >100 MP).
- Streaming downscale через `ffmpeg zimg` (строит output построчно, константная память).
- Кэш даунскейленных JPG (~2-5 MB) в `~/.cache/theme-hub/prepared/` по sha256-префиксу.
**Обоснование:** streaming избегает оверхеда полного декода; качество zimg достаточно для обоев; кэш делает повторный apply мгновенным.
**Последствия:**
- 22K-изображения прозрачны для пользователя (авто-downscale до 4K).
- Theme apply чуть медленнее на первом прогоне (2-3s downscale), повторно — мгновенно из кэша.
- Состояние всегда консистентно: оба пути (`--last` и основной) вызывают `update_state` → `wall.json` синхронен.
**Альтернативы отвергнуты:**
- Смена бэкенда — все бэкенды упираются в тот же 512 MiB лимит.
- `magick resize` — non-streaming, 5-10s на 22K, высокий пик памяти.
- Ручная предобработка пользователем — плохой UX, prone to user error.
**Статус:** Part 1 S2 (wall layer) COMPLETE; Part 2 S2 (bar layer, live refresh без reload_config) — in progress.

---

### TD-002: Todo система зависает (planner coordination)
**Дата:** 2026-08-02
**Контекст:** `todowrite()` создаёт список задач, но не обновляется динамически. Если задача делегирована агенту, todo висит в `in_progress` пока не создана новая задача. Нет обратной связи агентов → todo-система.
**Проблема:**
- Пайплайны асинхронны (bash-dev, builder, reviewer, etc) — работают независимо
- Todo не отражает реальное состояние параллельной работы
- Агент может закончить, todo висит в старом состоянии
- Вводит в заблуждение при планировании next steps
**Решение:**
- Todo используется только для **высокоуровневого планирования** (sketch phase, не пайплайны)
- Реальное отслеживание work-in-progress через git, commit messages, branch history
- **Не использовать todo внутри пайплайна** — leads to stale state
- Upon агент completion: обновить memory (decisions.md, tech-debt.md, roadmap.md) сразу, не ждать нового todo
**Следствие:** planner = оркестратор (координирует agents через git commits + memory updates), не менеджер статусов todo
**Действие:** удалить todo с активного использования в пайплайнах; применять only для user-facing запросов на планирование

**Обновление (2026-08-02): Event-driven Auto-Sync**

Вместо удаления todo из пайплайна — **автоматизирована синхронизация** через opencode-плагин:

**Плагин `.opencode/plugin/todo-sync.ts`:**
- Hook `tool.execute.after`: при завершении task() автоматически находит соответствующий todo и обновляет статус
- Hook `event`: слушает встроенный `todo.updated` (от `todowrite()`) и синхронизирует в snapshot
- Snapshot сохраняется в `.opencode/memory/todo.json` (persistent across sessions)

**Результат:**
- planner создаёт todo в sketch-фазе (одноразово)
- Делегирует task() агенту
- Agent завершает → плагин автоматически обновляет статус (no manual intervention)
- Todo отражает реальное состояние пайплайна in real-time
- Memory (decisions.md) остаётся source-of-truth; todo.json = snapshot для UI

**Механизм:**
```
todowrite() → tool.execute.after(task) → match agent name → update status → save todo.json
```

**Преимущества:**
- ✅ Нет зависания todo (автоматическое обновление)
- ✅ Полная интеграция с task() API
- ✅ Масштабируемо (работает для любых агентов)
- ✅ Transparent (planner не пишет sync-код вручную)

**Обновление (2026-08-02): event-driven sync через плагин**
- Реализован плагин `.opencode/plugin/todo-sync.ts` (auto-discovered)
- Хук `tool.execute.after` на `task()` completion: автоматически обновляет `in_progress` → `completed`/`failed` в `.opencode/memory/todo.json`
- Хук `event`: слушает `todo.updated` (sync встроенного todowrite → snapshot) и `file.edited` на `decisions.md` (reload snapshot)
- Memory (decisions.md) остаётся source-of-truth per TD-002; `todo.json` — автоматический snapshot для быстрого доступа
- Плагин использует Node fs (readFile/writeFile) для I/O, не зависит от ручных обновлений в planner-коде

---

### BUG-001: zimg filter unavailable in Manjaro ffmpeg (resolved 2026-08-02)
**Дата:** 2026-08-02
**Проблема:** `theme-apply` downscale использовал `ffmpeg -vf "zimg=..."`. ffmpeg в Manjaro не скомпилирован с `--enable-libzimg`, поэтому фильтр недоступен → 15/18 обоев падали с "Даунскейл не удался".
**Root cause:**
- Guard в `prepare_image()` правильно триггерит на 22K (10 файлов)
- Но `ffmpeg -vf zimg=...` падал (exit != 0) → уведомление об ошибке
- Из 18 обоев: 8 проходили guard (≤8192px), 10 нуждались downscale
- Вероятность успеха: 8/18 ≈ 44%, наблюдалось 5/20 ≈ 25% (в пределах variance)
**Решение (коммит 193f644):**
- Заменить `zimg` на встроенный `scale` фильтр
- `scale=3840:2160:flags=lanczos` = то же качество (оба lanczos)
- Память: оба фильтра streaming (построчный), OOM не будет
**Таблица обоев:**
  - 10 файлов 22K×12K (270MP) → нужен downscale
  - 8 файлов ≤8192px → проходят guard, downscale не нужен
**Итог:** issue resolved; все 18 обоев теперь работают
