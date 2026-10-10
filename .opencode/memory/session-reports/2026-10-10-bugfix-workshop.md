# Мастерская «БагФикс» — реестр инцидентов (2026-10-10)

Сессия-мастерская: агенты/пользователь приносят баги, итоги копятся здесь для
будущего спец-агента по отладке. Формат каждого: symptom → repro → root cause →
fix/workaround → evidence → status.

---

## INC-1 — `skill "" Invalid arguments, id Missing key`

- **Symptom:** вызов тула `skill` падал с `Invalid arguments, id Missing key`.
- **Repro:** любой вызов skill через плагин `fix-tool-schema.ts` на OpenCode v2.0.26.
- **Root cause:** ядро OpenCode v2 (v2.0.26) ждёт у тула `skill` обязательное
  поле `id` (вызов `{"id":"<skill-id>"}`), а плагин слал старую схему с `name` —
  ядро отбивало как `id Missing key`. Подтверждено доками v2 и `src/tool/skill.ts`.
- **Fix:** `SKILL_FLAT` переведён на `id` (required `["id"]`, плоская схема без
  oneOf/anyOf; `name` оставлен deprecated-алиасом).
  Файл: `opencode-global/.config/opencode/plugins/fix-tool-schema.ts`.
- **Evidence:** bun build OK, verifier PASS. Коммит `00e2910` (ветка
  `task/skill-id-fix`). Живьём подхватывается после рестарта TUI (плагин не hot-reload).
- **Status:** fixed, shipped.

---

## INC-2 — verifier спотыкается: не читает файл / виснет на подтверждении

- **Symptom:** verifier (локальный и глобальный) не мог посмотреть выданный файл
  или запрашивал подтверждение простой команды; при отсутствии пользователя
  вызов висел и verifier падал.
- **Repro:** verifier вызывает любую повседневную команду → `bash "*": ask` →
  запрос подтверждения; нет реакции → зависание → падение.
- **Root cause:** в permission-блоках verifier базовое правило было `bash "*": ask`.
  Падение — именно от `ask` (висит без ответа), не от `deny` (fail-fast).
- **Fix:** снят весь `ask` в 4 местах — `.opencode/agent/verifier.md`,
  `opencode-global/.config/opencode/agent/verifier.md`, два блока verifier в
  `opencode.json` (object-style `permission` и array-style `permissions`).
  Стало: `read/glob/grep/webfetch/external_directory = allow`, `bash "*": allow`,
  `deny` только на разрушительном (rm -rf, push --force, reset --hard, clean,
  chmod/chown, systemctl stop/disable/mask, mkfs/shutdown/reboot). `edit=deny`
  сохранён как суть роли (fail-fast, не виснет).
- **Evidence:** JSON валиден (`python3 -m json.tool`), коммит `8f6e8c7`
  (ветка `task/verifier-unrestricted`).
- **Status:** fixed, shipped. Acceptance gate — живой прогон verifier без единого
  `ask` после рестарта TUI (конфиги не hot-reload).

---

## INC-3 — `session_move Unable to move session to <path>`

- **Symptom:** `session_move` verifier-сессии в существующие каталоги возвращал
  `Unable to move session to <path>`; сессия не переносилась.
- **Repro:** `session_move(sessionID=<verifier>, directory=<существующий абс. путь>)`;
  наблюдалось для `/home/rudra/Projects` и
  `/home/rudra/Projects/OpenCode-Vault-tasks/ssa-bootstrap-20261010`.
- **Root cause:** ядро OpenCode v2.0.26. Встроенный тул `session_move`
  (`packages/core/src/tool/plugin/opencode.ts`) оборачивает разные внутренние
  ошибки (`SessionMove`, инициализация контекста назначения) в один общий текст —
  конкретную причину по нему не извлечь. В dotfiles перехватчика/обработчика
  `session_move` нет; `external_directory` у verifier = allow. Dotfiles-причина
  не подтверждена.
- **Доп. расследование (2026-10-10, после push-back Макса):** воспроизвёл сам
  своим тулом `session_move` (primary) → та же `Unable to move session to …`.
  Значит это НЕ нехватка capability у вызывающего (verifier-субагента),
  ошибка настоящая и на моём инструменте. По исходнику v2.0.26 общий текст —
  обёртка над одной из: `NotFoundError` (сессии нет), `DestinationNotFoundError`,
  `DestinationNotDirectoryError`, `DestinationUnavailableError` (не поднялся
  project-контекст назначения).
- **Ведущая причина (evidence, линковка `[проверить]`):** в логах — серии
  `Failed to drain Session … Session.AgentNotFoundError: Agent not found: "meta"/"sysop"/"librarian"`.
  Эти агенты определены **проектно-локально** (`dotfiles/.opencode/agent/*.md`),
  а целевые каталоги (`/home/rudra/Projects`, SSA bootstrap-worktree) лежат вне
  dotfiles и этих определений не имеют. При переносе сессия просыпается в новом
  каталоге, `prepareContext → SessionContext.select` не находит её активного
  агента → drain падает → ядро отдаёт общий `Unable to move session`. Точная
  привязка именно к моей попытке move во времени не зафиксирована — `[проверить]`.
- **Fix/workaround:** чужой harness (ядро OpenCode) не патчим. Рабочий путь —
  (а) открывать сессию сразу в целевом worktree, либо (б) делать roaming-агентов
  **глобальными** (`~/.config/opencode/agent/`, копии уже есть в
  `opencode-global/.config/opencode/agent/`), чтобы контекст назначения
  резолвил агента в любом каталоге. Прямую правку БД сессий не делать.
- **Evidence:** v2.0.26; целевые каталоги существуют/доступны; собственный
  вызов `session_move` воспроизвёл ошибку; лог `AgentNotFound` при drain.
  Источники: v2.0.26 `session/move.ts`, `tool/plugin/opencode.ts`,
  `~/.local/share/opencode/log/opencode.log`.
- **Status:** диагностировано (ведущая причина — локальный агент не резолвится
  в каталоге назначения). Чистого dotfiles-фикса в патче ядра нет; обходы (а)/(б)
  доступны. Core-поведение (маскировка причины общим текстом) — `[проверить]`,
  баг ядра.

---

## INC-4 — субагент падает: `only "auto" is supported for tool_choice`

- **Symptom:** спавн субагента (builder) падал: `only "auto" is supported for
  tool_choice. "none", "required", and named function choices are not currently
  supported`.
- **Repro:** `task(agent=builder …)` на провайдере `justwoker`; ядро/AI SDK
  при спавне форсирует инструмент (`tool_choice` ≠ auto) → upstream отбивает.
- **Root cause:** в наших конфигах `tool_choice` нигде нет — его шлёт
  OpenCode/AI SDK. Upstream `api.justwoker.icu` (New API gateway) принимает
  только `tool_choice:"auto"`; на `none`/`required`/named отвечает ошибкой и
  роняет ход. Наш транспорт `justwoker-shim.ts` форвардил тело как есть.
- **Fix:** в `route()` шима добавлена нормализация: если `tool_choice` присутствует
  и не `auto` (строка или объект) — переписываем в `auto` и пере-сериализуем тело
  (только когда реально меняем; иначе форвард сырым `raw`). Покрывает оба пути
  (stream synthesis, non-stream passthrough) и OpenAI-фасад (через `parsed`).
  Инструменты остаются доступны — просто не форсируются.
  Файл: `opencode-global/.config/opencode/shim/justwoker-shim.ts`. Коммит `d6446f5`.
- **Evidence:** `bun build` шима — OK (bundled, без ошибок); `raw`/`parsed`
  переиспользуются на всех форвард-путях (строки 510/593 и фасад).
- **Status:** fixed. Acceptance gate — живой спавн субагента без ошибки
  tool_choice **после рестарта systemd-юнита шима** (транспорт не hot-reload).

---

## Процессный урок (peer-comms)

Получив баг-хэндофф, primary обязан по протоколу писем (B18) слать `started`
при получении и `finished` при завершении через `tools/peer-comms/letter.sh`
(без `-m`, идемпотентно по message_id). В этой сессии баги пришли прямым прометом
(не через канонический журнал — в `receipts-out.jsonl` входящего на сессию нет),
поэтому формальная квитанция не ушла. Урок: при живом канале закрывать петлю
`started/finished`, если известен session_id отправителя и message_id (`--ref`).

---

## INC-5 — `external_directory` блокирует sibling-worktree и `/tmp/opencode`

- **Symptom (BAGFIX-LETTER, basis: quoted):** в librarian-сессии с workspace
  `/home/rudra/Projects/OpenCode-Vault` команды `git push` и даже
  `git remote get-url origin` из
  `/home/rudra/Projects/OpenCode-Vault-tasks/ssa-bootstrap-20261010`, а также
  `write` в `/tmp/opencode/<file>` возвращали
  `permission.rejected: Permission denied: external_directory`. Из того же
  worktree `git add`/`git commit` прошли; push из workspace-root с refspec
  прошёл. Shell-запись в `/tmp/opencode` также проходит.
- **Repro:** BAGFIX-LETTER, 2026-10-10, repro A/B; сообщение об ошибке дано
  дословно в поручении.
- **Root cause (ведущая, runtime-привязка `[проверить]`):** конфиг активного
  корня Vault содержит `external_directory: {"*":"deny", ...allowlist...}`.
  В allowlist есть основной `OpenCode-Vault/**`, но нет sibling
  `OpenCode-Vault-tasks/**` и `/tmp/opencode/**`. Конфиг task-worktree включает
  `OpenCode-Vault-tasks/**`, но сессия была открыта из основного Vault —
  подтверждение, какой project config применён при обоих вызовах, требует live
  repro. `git rev-parse --git-common-dir` worktree разрешается под основным
  Vault (`.git/worktrees/...`), который allowlisted; гипотеза «common `.git`
  вне allow-scope» этим не подтверждается. Ранее записанный Vault-метод также
  отмечает возможный отказ `write` на внешних temp-путях.
- **Fix:** для активного сбоя нужен change в Vault-owned `opencode.json`:
  согласовать allowlist sibling worktrees и требуемого temp-каталога при
  сохранении deny секретов. В dotfiles не менял permission-конфиги вслепую:
  глобальный dotfiles-конфиг уже `allow` + secret-deny. Изменение Vault вне
  разрешённого scope dotfiles; создан handoff владельцу Vault.
- **Evidence:** прочитаны оба Vault `opencode.json`, librarian frontmatter,
  Vault `02-Methods/incident-fix.md`; установлен фактический git common-dir.
  Live permission-repro не запускался из этой сессии.
- **Status:** root cause вероятна, подтверждение runtime `[проверить]`;
  исправление ждёт Vault-owned change. Не объявлять fixed.

---

## INC-6 — повтор сигнатуры skill tool `id: Missing key` (корреляция INC-1)

- **Symptom:** вызов доступного skill-инструмента с объявленным аргументом
  `name: tree-hygiene` вернул `Invalid arguments ... id: Missing key`.
- **Repro:** первичная попытка загрузить skill перед этой работой; skill затем
  прочитан напрямую из `.opencode/skills/tree-hygiene/SKILL.md`.
- **Correlation:** сигнатура совпадает с INC-1 (`00e2910`, исправлен
  `fix-tool-schema.ts`: runtime skill schema использует `id`). Это повторное
  наблюдение, не второй подтверждённый dotfiles-root-cause. Слой вызова здесь —
  developer skill-tool adapter; связь с INC-1 runtime fix пока `[проверить]`.
- **Fix/workaround:** runtime fix INC-1 не переоткрывается без repro на самом
  OpenCode skill tool. В этой сессии инструкцию прочитал прямым read.
  Включить сигнатуру как tool/channel fixture в `BF-20261010-01`, сохраняя
  отдельный source-layer в записи.
- **Evidence:** точный отказ вызова и успешное чтение
  `.opencode/skills/tree-hygiene/SKILL.md`; ранее shipped INC-1/`00e2910`.
- **Status:** коррелирован с INC-1, adapter-layer не подтверждён; наблюдать,
  не считать отдельным неисправленным dotfiles-инцидентом.

---

## BF-20261010-01 — программное правило «сбой → багфикс»

- **Symptom/trigger:** сбой инфраструктуры может быть обойдён или скрыт без
  обязательного incident record и письма в мастерскую.
- **Repro:** перечисленные в BAGFIX-LETTER классы ошибок (permission.rejected,
  tool/channel, plugin/script, model/quota); дополнительно INC-6 — tool-schema
  failure.
- **Root cause:** спека `docs/specs/bugfix-proactive-plugin.md` (под substance
  получила approval Рудры 2026-10-07, но во frontmatter всё ещё `status: draft`)
  фиксирует capture/handoff, но запрещает auto-dispatch и оставляет letter
  маршрут за отдельным мандатом.
- **Fix:** отдельная execution spec `docs/specs/bugfix-failure-rule.md`, ID
  `BF-20261010-01`, статус `proposed`; включает канон `letter.sh`/B18,
  шаблон symptom→repro→root cause→fix→evidence→status, command/registry,
  metadata-only capture, dedup, cost/false-positive gates, fail-visible маршрут
  при отсутствии активной роли `bugfix`. Runtime enforcement не включать до
  отдельного approval Rudra.
- **Evidence:** статическая сверка draft-спеки плагина (substance approved
  Рудрой) и B18;
  claims registry сейчас не содержит активной роли/session `bugfix`.
- **Status:** proposed; reviewer→verifier до approval; runtime реализация
  заблокирована до явного approval Rudra.
