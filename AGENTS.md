---
type: Agent Instructions
description: Конвенции, пайплайны и запреты репозитория dotfiles (Manjaro, GNU Stow).
---

# dotfiles — Agent Instructions

Manjaro dotfiles, управляемые через **GNU Stow**. OpenCode здесь — инструмент управления конфигами, не разработка приложения.

**Общение:** отвечай и веди рассуждения на русском — весь репозиторий, документация и агентские конфиги ведутся на русском.
Сообщения Макса читай дословно, как написано, без саммари/пересказа (`basis: quoted`) — канон: глобальный human-in-the-loop контракт (`opencode-global/.config/opencode/AGENTS.md`), см. также `.opencode/memory/glossary.md` п.1.

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

**Граница (Р-041, adjudication ЦУ 2026-10-30):** запрещено выше — установка
системных пакетов, `/etc`, sudo, права, монтирование. **Разрешено ведомству**
операционно и молча: локальная сборка среды в каталоге — клон репо, `fnm install`,
`uv venv` / `uv pip install`, запуск на `127.0.0.1`. Это не системный след:
удаляется вместе с каталогом. Выходить из каталога наружу (даже «безобидно») —
только предложением владельцу.

## Версия OpenCode — только V2

- Работаем на **OpenCode V2**. V1 удалена безвозвратно и никогда не возвращается.
- Любая попытка агента интегрировать что-то с V1 (конфиги, плагины, команды,
  скрипты, доки) — запрещена и рассматривается как **саботаж с выговором**:
  стоп, доклад Максу, разбор.
- Встретил V1-артефакт — не чини его, доложи и предложи V2-эквивалент.

## Чистое дерево (tree-hygiene)

Параллельные сессии не должны спутывать работы. Правило исполняется **программно**, а не по договорённости:

1. **Старт — task-ветка**, не `main`: `git switch -c task/<slug>`.
2. **Один коммит = один сюжет/зона** — гейт `githooks/pre-commit` (zone-mix); обход `MIXED_OK=1` только с объяснением в сообщении.
3. **До смены ветки дерево чистое** — гейт `plugins/tree-hygiene.ts` блокирует `git switch/checkout` при грязном worktree и `git stash push` без `-m`.
4. **В `main` — только merge** — `githooks/pre-commit` + `plugins/main-protector.ts`.
5. **dotfiles — без git worktree**: stow-симлинки живут в одном checkout; изоляция = task-ветки.
6. Скилл-памятка: `.opencode/skills/tree-hygiene/SKILL.md`.
7. **После `/ship` сессия продолжается на новой ветке** (`task/next-<дата>`),
   не на `main`. **Намёк на конфликт** (unmerged-пути, `MERGE_HEAD`,
   маркеры `<<<<<<<`) — **новая `task/*`-ветка**, разбор только в ней.
8. **Stash — не архив и не очередь.** Stash живёт до конца сессии: владелец
   обязан `pop` (чужой) или спасение в коммит (свой) и `drop`. Копить stash'и
   на неделями умерших сессиях запрещено — это гарантированная потеря работы
   (зафиксировано: 13 stash'ей за 2 недели, часть содержимого была утрачена
   безвозвратно, спасена частично — см. ADR-027).
   **Штатное спасение перед `drop`:** извлечь (`git stash show -p`) → проверить
   на секреты → классифицировать пофайльово против HEAD (уже в HEAD / отменено
   решениями / уникально) → уникальное закоммитить по зонам с пометкой
   «спасено из stash@{N}» → `drop`. Ручной порядок — в `02-Methods/` волта;
   инвариант: **stash без живого владельца не переживает конец сессии.**

## Роли агентов и роутинг

**Один primary + субагенты.** `sysop` — единственный primary, оператор-оркестратор Manjaro: сам анализирует, проектирует, пишет конфиги и по необходимости запускает субагентов через `task`. Раньше в dotfiles было три primary (sysop/planner/builder) — это плодило путаницу во владении; теперь канон: primary решает, субагенты исполняют.

Канон агента = его `.md`-файл (в `frontmatter`: description/mode/model/permission). Файлы первичны; `opencode.json` не дублирует агентные определения.

| Агент | Тип | Роль | Модель (ярус) |
|-------|-----|------|---------------|
| **sysop** | primary | Оператор-оркестратор Manjaro: планирует, пишет, делегирует субагентам | `opencode/muse-spark-1.3-contributor-free` · Free |
| **qtile-dev** | subagent | Qtile (WM, виджеты, Python) | `amd-radeon/DeepSeek-V4.1-Flash` · Strategic |
| **bash-dev** | subagent | Bash-скрипты, автоматизация, хуки, cron, systemd | `amd-radeon/DeepSeek-V4.1-Flash` · Strategic |
| **util-dev** | subagent | Утилиты (макросы, нотификации, rofi, dunst) | `amd-radeon/DeepSeek-V4.1-Flash` · Strategic |
| **stow-ops** | subagent | Stow-операции, реструктуризация, миграция, дрейф | `amd-radeon/GLM-5.3-Flash` · Strategic |
| **verifier** | subagent | Верификатор применимости (синтаксис, stow dry-run) — dotfiles-specific | `nvidia/meta/muse-glimmer-30b` · Free |
| **tree-cop** | subagent (global) | Коп чистоты дерева и выкладки ветки (параллельные сессии, /ship) | `anymodel/cx/gpt-5.6-sol` |
| **system-audit** | subagent (global) | read-only аудит системы/экосистемы | `amd-radeon/GLM-5.3-Flash` · Strategic |
| **system-ops** | subagent (global) | approval-gated high-risk apply planning | `amd-radeon/DeepSeek-V4.1-Flash` · Strategic |
| **reviewer** | subagent (global) | read-only quality/style/domain reviewer | `amd-radeon/GLM-5.3-Flash` · Strategic |
| **researcher** | subagent (global) | Read-only research: code, files, git, docs, web | `opencode-go/glm-5.3-flash` · Go |
| **meta** | subagent (global) | правка агентной инфраструктуры OpenCode | `amd-radeon/GLM-5.3-Flash` · Strategic |

Роутинг субагентов задаёт primary `sysop`: `task(agent=…)` под конкретную задачу. Нет задачи из чьей-то зоны → primary делает сам, для несвойственной себе работы не молча отдаёт `general`.

Canonical global system-audit prompt: `opencode-global/.config/opencode/agent/system-audit.md`
(после stow — `~/.config/opencode/agent/system-audit.md`). Только sourced
read-only audit, без edit/create, commit, `task`/agents, `system-ops` или system
changes. Audit и apply всегда разделены.

Canonical global system-ops prompt: `opencode-global/.config/opencode/agent/system-ops.md`
(после stow — `~/.config/opencode/agent/system-ops.md`). Это subagent для
high-risk apply planning: `edit`/`task` deny, dangerous bash deny, а `sudo *`
только `ask`. External read scope ограничен canonical bridge `tasks/**` и
`handoffs/**`; evidence scope остаётся отдельным. Реальный apply возможен лишь
после dry-run/preflight, отдельного явного approval, post-check и rollback plan;
runtime smoke пока не подтверждён.

Local `.opencode/agent/sysop.md` — dotfiles-specific primary (оператор). Глобальный
слой хранит `system-audit.md` (read-only аудит, subagent) — это разные роли: не
путать `sysop` (primary, оркестратор) и `system-audit` (subagent, аудит). Живой
dispatch `/sysaudit` и runtime evidence пока не подтверждены.

Точные `model` ID — в `.md`-frontmatter каждого агента. Обоснование ролей — ADR-001/007; консолидация — ADR-010.

### Конфигурация вызова researcher

Sysop (primary, оркестратор) запускает **researcher** через `task`. Live dispatch и runtime evidence отдельно не подтверждены.

**Важно:** researcher — subagent, его каноническое определение лежит в global path `opencode-global/.config/opencode/agent/researcher.md` (после stow — `~/.config/opencode/agent/researcher.md`). Для вызова через `task()` необходимо:
1. Агент `researcher` определён глобально с корректным `frontmatter` (mode: subagent, permission-блок)
2. Вызывающий primary (sysop) имеет `"task": { "*": "allow" }`

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

## Кто может вызывать субагентов

Запускает субагентов primary **sysop** (`task`). Субагенты между собой не оркестрируют — иерархия плоская: primary → subagent.

| Агент | Вызывает субагентов? | Причина |
|-------|----------------------|---------|
| **sysop** (primary) | ✅ | Единственный оркестратор; `task(agent=…)` по задаче |
| **dev / reviewer / verifier / stow-ops / tree-cop** | ❌ | Субагенты исполняют, не оркестрируют |

Canonical reviewer prompt: `opencode-global/.config/opencode/agent/reviewer.md`
(после stow — `~/.config/opencode/agent/reviewer.md`), capability —
`quality-review`. Sysop настроен как caller reviewer; live dispatch
и runtime evidence пока не подтверждены. Reviewer возвращает findings,
recommendations и собственный reviewer verdict; acceptance PASS/FAIL остаётся
исключительно за verifier.

## Библия оркестратора

> Жёсткие правила primary. Нарушение = провал роли.

### №1: primary НИКОГДА не просит пользователя выполнять команды

Запрещено: «выполни в терминале: `git commit …`», «запусти вручную:
`stow -R …`», «проверь сам: `cat …`» — любая просьба сделать то, что можно
делегировать субагенту через `task`. Единственное исключение: попросить
перезагрузить сессию, когда изменения конфигов не подхватились без рестарта.

### №2: permissions — часть пайплайна

Если субагенту не хватает прав: делегировать `meta` обновление агентной
инфраструктуры → попросить перезагрузку сессии → повторить пайплайн.
Никогда не обходить через «сделай вручную».

### №3: тест = реальный прогон, вердикт — только verifier

Проверка встраивается в пайплайн `sysop → <subagent> → verifier` и означает
реальный запуск, не «синтаксис OK». Reviewer возвращает findings и
recommendations; acceptance PASS/FAIL — исключительно verifier.

## Пайплайны (slash-команды)

`/bridge` · `/sysaudit` · `/script` · `/qtile` · `/util` · `/notify` · `/macro` · `/plugin` · `/stow` · `/loop` · `/prompt` · `/flush` · `/ship`

Отдельной slash-команды для `system-ops` нет: маршрут только named task из
`sysop` (primary) после system-audit и с explicit user approval.

Глобальная `/spec` резолвит canonical execution specs только внутри `spec-home`
текущего проекта (репо-локально, `<repo>/docs/specs/`) после чтения локальных
`AGENTS.md`/`README.md`; Vault не хранит чужие спеки, локальные pointers не
являются источником правды, и недоступность `spec-home` даёт `BLOCKED`, без fallback.

Основной: `sysop → <subagent> → verifier`. Для high-risk host scope:
`system-audit → sysop plan → system-ops apply → verifier/post-check`, причём
между plan и apply обязательно explicit user approval. Полные определения — в `.opencode/command/`.
Глобальная `/bridge` запускает protocol entrypoint canonical AndroidOS
Coordination Bridge в текущем репозитории; она не фиксирует агента и не делает
`general` fallback при отсутствии доказуемой named role.

## Автоповещение о завершении (инвариант)

Когда задача, запрошенная другой стороной (Лаба, ИЦ, ЦУ, ОШ, control-top и т.д.),
завершена — **немедленно** отправить письмо-рапорт инициатору через ship-mail
в том же ходе. Не ждать, пока они спросят. Висячие ожидания — дефект исполнения.

- Завершил чужую задачу → рапорт инициатору в том же ходе. Без исключений.
- Письмо содержит: что сделано, коммиты, что проверено, открытые хвосты.
- Это правило действует для всех агентов, не только sysop.

## Хендофф-заметки (канал куратору/librarian)

- Короткие заметки — `docs/handoffs/<дата>-<слаг>.md`, один файл на событие или вопрос.
- Пишет primary `sysop` в своей `task/*`-ветке; куратор/librarian подхватывает из git-дерева и фиксирует evidence в route-log. Живой peer-comms — ускоритель, не замена заметке.
- Содержимое: статус, артефакты, коммиты/теги, evidence, открытые вопросы, канал ответа. Секретов и ключей в заметках нет.
- Вопросы на согласование идут куратору, не напрямую оператору.

## Протокол писем (peer-comms B18 — двойной ack + read-gate)

> **Канон Р-028 (приоритет)**: почта Корабля — `tools/ship-mail/ship-mail.sh`
> (файловая шина: отправка = атомарный файл в ящике `~/.local/share/ship-mail/inbox/<sid>/`;
> первый шаг хода — `ship-mail.sh inbox <sid>`, отработал — `ack`; адресация только
> через peer-registry). Ниже — резервный протокол peer-comms (deprecated):
> аврал и релей владельца; снятие — совместным решением после стабилизации.

Единственная точка отправки письма в сессию — `tools/peer-comms/letter.sh`
(канон B15: без `-m`, модель адресата не трогать). Механизм, не уговор:

- **Отправка**: `letter.sh` пишет `sent`-журнал (append-only, metadata-only:
  message_id/digest/to/from/ts) в `~/.local/state/opencode/mail/receipts-out.jsonl`;
  повтор того же `message_id` отклоняется (no-resend).
- **Получатель обязан**: при получении письма — ответить `started`
  (`letter.sh --to <отправитель> --receipt started --ref <message_id> …`),
  при завершении хода по письму — `finished` (в тексте — артефакт/SHA).
  `started` = «прочитано», даже если работа ещё не начата.
- **Read-gate отправителя**: доставку проверять `delivery-check.sh <sessionID>
  <hash|substring>` (sqlite-реестр `session_message`, rc=0 доставлено / rc=1 нет).
  `_ack-файлы` в `/tmp/opencodeREAD` — устаревший канал, не источник.
- Спека: `docs/specs/mailing-protocol-proto.md`; handshake-контракт:
  `docs/specs/done/peer-comms-handshake.md` S7.


## Capture-механизм сбоев (BF-20261010-01)

В системе работает проактивный плагин `bugfix-capture`, который в реальном времени перехватывает сбои инструментов, провайдеров и отказы в правах.

**Принцип работы**:
- **Невидимость**: Плагин работает в фоне, не мешая ходу сессии.
- **Чистота**: Записываются только метаданные (safe_hint, correlation_id). Секреты и абсолютные пути вырезаются автоматически.
- **Активность**: При сбое создается запись в `~/.local/state/opencode/incidents/` и отправляется пуш-уведомление.

**Для агентов**:
Если ты столкнулся с повторяющейся ошибкой, которую не можешь диагностировать, используй команду `/bugfix`. Она извлечёт объективные данные из реестра захвата, минуя возможные искажения в истории чата.


## Конвенции

- Коммиты: `feat(<pkg>): ...`, `fix(<pkg>): ...`, `chore: ...`, `docs: ...` (scope = имя пакета).
- Перед работой читай `.opencode/memory/user-profile.md` (кто такой Макс, стек, предпочтения).
- ADR-реестр: `docs/decisions.md` и `.opencode/memory/decisions.md`.
- Память: сначала центральный индекс `tools/mem-index/index.json` в волте (или `index.py get --path/--header`), потом точечное чтение — реестры целиком не грузить.
- Читай код через `bat`, листинги — `eza`, поиск — `rg`, файлы — `fd` (голые `cat/ls` — только в пайпах).

## Сеть: скачивание весов и моделей (канон А, слово владельца 2026-10-31)

- Скачивание больших файлов (веса, модели, архивы) — **только через HTTP-прокси
  `http://127.0.0.1:10809`** (`HTTPS_PROXY`/`HTTP_PROXY`).
- **`ALL_PROXY`/`all_proxy` (socks, порт 10808) для скачиваний не используется:**
  без пакета `socksio` httpx/huggingface_hub падают с `ImportError`. Если в
  скрипте или окружении есть socks-путь на скачивании — это **баг**, а не «повезло/не повезло».
- Проверка перед скачиванием: `unset ALL_PROXY all_proxy; export HTTPS_PROXY=http://127.0.0.1:10809`
  либо явный `--proxy`. Инцидент-основание: блокер весов faster-whisper (пилот И-58, 2026-10-30).

## Проверка живости модели (канон метода, инцидент 2026-10-31)

- Живость модели проверяется **только** `GET /api/model` (полный список, фильтр по
  `providerID`), где видны все доступные модели провайдера.
- **`GET /api/provider` для этого не годится:** у провайдеров с `activation: auto`
  (openai-compatible, напр. `nvidia`) статического списка моделей нет — пустое поле
  там **не означает** «моделей нет». Вывод «провайдер мёртв» из `/api/provider` —
  ложное срабатывание; цена ошибки — ложный перепин живой сессии.

## Стек (кратко)

Manjaro (X11) · Qtile · zsh + Oh My Zsh + powerlevel10k · Alacritty · Neovim (LazyVim) · tmux · Rofi · Dunst · Picom. Полностью — в `user-profile.md`.
