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
- **Root cause (уточнено после apply):** не «нет правила», а **отставший
  checkout**. Нужные allow-строки уже есть в `origin/main` Vault (коммит
  `cac2a00` «permission preflight for worktrees»: `OpenCode-Vault-tasks/**`,
  `dotfiles-tasks/**`), но основной рабочий checkout Vault стоял на отошедшей
  от main task-ветке `task/pipboy-rebuild-20261009`, чья версия `opencode.json`
  эти строки не содержит. Сессия librarian открыта из основного корня →
  применялась отставшая версия файла. Отказ `external_directory` — прямое
  следствие. Гипотеза «common `.git` вне allow-scope» опровергнута:
  `git-common-dir` лежит в allowlisted основном Vault.
- **Fix (применён 2026-10-10, мандат Рудры):** `git checkout origin/main --
  opencode.json` в чужом checkout Vault; JSON валиден, обе allow-строки на
  месте, секретные `deny` сохранены. Оставлено uncommitted в чужой task-ветке —
  коммит в неё бессмыслен (строки уже в main), переключение/merge чужой dirty
  ветки не моя зона.
- **Evidence:** прочитаны оба Vault `opencode.json`, librarian frontmatter,
  Vault `02-Methods/incident-fix.md`; установлен git common-dir; сверка
  HEAD↔origin/main показала регрессию файла именно в отошедшей ветке.
  Live permission-repro после apply не запускался.
- **Status:** fixed (apply выполнен, файл рабочего дерева == origin/main).
  Residual: (1) **закрыт 2026-10-13, live-прогон из корня волта
  `/home/rudra/Projects/OpenCode-Vault` (workdir, ветка `task/pipboy-rebuild-20261009`):**
  `write`-инструмент создаёт файл в корне — OK; python write+unlink — OK;
  `git push --dry-run origin HEAD` rc=0 (`* [new branch]`) локальные git-команды из
  корня волта работают — push к волту жив. Тестовые артефакты `.inc5-*` убраны.
  (2) остаётся `[проверить]`: при будущем merge `pipboy-rebuild` в main —
  conflict-check по `opencode.json`, чтобы не откатить `cac2a00`.

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

---

## INC-7 — хоткей `Super+o` (opencode-reload) «перестал работать»

- **Symptom:** жалоба Рудры: не срабатывает `Super+o` (перезагрузка backend'а
  OpenCode через `scripts/.local/bin/opencode-reload`).
- **Repro:** нажатие `Super+o` не давало перезапуска `opencode serve --service`.
- **Root cause (две составляющие, конфиги невиновны):**
  1. **Grab-race в qtile (2026-10-09):** 398 ошибок `Can't grab ... unknown
     keysym` на 32 клавишах, включая `Super+o`. При старте/reload X-сервер не
     успевал отдать keysym'ы — qtile физически не захватил клавишу, нажатие не
     доходило до обработчика. Конфиг валиден (`keys.py`, скрипт синтаксис OK),
     дублей по `Super+o` не было.
  2. **dunst мёртв:** `dunst.service` в `inactive (dead)` — скрипт шлёт
     `notify-send`, уведомления нет, срабатывание невидимо.
- **Fix:**
  1. `qtile cmd-obj -o cmd -f reload_config` — пере-grab клавиш, ошибок нет.
     Живой тест `xdotool key --clearmodifiers super+o`: PID
     `opencode serve --service` сменился — хоткей работает.
  2. Рудра запустил `systemctl --user start dunst.service` — нотификации вернулись.
- **Попутная правка (dotfiles, ревизия 2026-10-11 по уточнению Рудры):**
  дубль `Super+Shift+T` в `qtile/.config/qtile/keys.py` был двумя привязками —
  `tmux-open` (стр.39) и `conky-toggle` (стр.49). Рудра не пользуется Conky и
  просил хоткей именно на `tmux-open`; живым оставлять нужно `tmux-open`.
  Удалена строка `conky-toggle` — `Super+Shift+T` теперь открывает сохранённую
  tmux-сессию через `alacritty -e tmux-open`. (Первоначально в `ff1fee5` была
  удалена мёртвая `tmux-open`-строка — по ошибке; исправлено этой ревизией.)
  `conky-toggle` из keys.py убран полностью; сама утилита `conky-toggle` не
  тронута.
- **Evidence:** `~/.local/share/qtile/qtile.log` (398 grab-ошибок 2026-10-09,
  0 после reload 2026-10-11); `systemctl --user status dunst.service`;
  смена PID бэкенда после `xdotool super+o`.
- **Status:** fixed. Residual `[проверить]`: grab-race — разовый X/qtile race,
  при повторе смотреть старт X-сессии; `tmux-open`-хоткей при желании
  перепривязать на свободную клавишу (отдельная задача, не делал).

---

## INC-8 — read-only агенты не открывали внешние файлы (vault), 9 жалоб за месяц

- **Symptom:** Рудра: «в волта "Reviewer не смог открыть внешний dotfiles-файл" —
  я думал проблема решена... уже 9 раз прошу за последний месяц». Отказ чтения
  файлов вне рабочей директории у read-only агентов; возвращалось многократно,
  потому что чинилось симптоматически (то bash-allowlist, то проектный конфиг),
  а не по root cause.
- **Repro:** вызвать `researcher`/`reviewer` с задачей прочитать файл вне
  workspace (например `/home/rudra/Projects/OpenCode-Vault/04-Memory/facts.md`)
  → отказ на инструменте чтения.
- **Root cause:** в `opencode-global/.config/opencode/agent/researcher.md`
  ключ `external_directory` **отсутствовал полностью**. Без него действовал
  дефолт проекта/глобального слоя, а при конфликте слоёв выигрывал более
  строгий — внешнее чтение перекрывалось. Дополнительная слабость: у ряда
  агентов стоял скалярный `external_directory: allow`, который при last-match-wins
  **затирает** секретные deny глобального слоя (`.env`, `*.key`, `id_rsa`…).
- **Fix (dotfiles, коммит `7c80690`):**
  1. `researcher.md`: добавлен `external_directory` в **object-форме** —
     `"*": allow` + все секретные deny (идентично глобальному `opencode.jsonc`).
     Внешнее чтение открыто, секреты закрыты, `edit`/`task` остались `deny`
     (read-only семантика не тронута).
  2. `reviewer.md` уже имел `external_directory: allow` — работает.
- **Evidence (живые прогон 2026-10-13):**
  - `researcher` → `ses_ecd1eaf5fffesx7BMVTn1VchBO`: vault-файл прочитан
    (первые 2 строки дословно, 962 строки); `shell` корректно отклонён
    (`permission.rejected: Permission denied: shell`) — read-only держится.
  - `reviewer` → `ses_ecd1e398dffeeWnIYUAnsM72pe`: vault-файл прочитан.
  - Правка уже в рантайме без рестарта: `~/.config/opencode/agent` — симлинк
    на каталог репо, `researcher.md` имеет один inode в обоих путях.
- **Root-cause примечание (почему 9 раз):** `~/.config/opencode/agent/*.md` —
  это симлинк-каталог `agent/` → `dotfiles/opencode-global/.config/opencode/agent`,
  то есть правки репо **сразу** в рантайме. Повторные жалобы шли не из-за
  отсутствия рестарта, а из-за точечных фиксов: чинили bash-whitelist и
  проектный конфиг, но не сам отсутствующий ключ `external_directory`.
- **Status:** fixed, подтверждено живыми прогонами обоих агентов.
- **Residual `[проверить]`:** `meta`, `system-audit`, `tree-cop` по-прежнему
  **без** ключа `external_directory` (таблица инвентаризации) — если им понадобится
  внешнее чтение, понадобится тот же object-фикс. Скалярные `allow` у
  `bash-dev`/`qtile-dev`/`stow-ops`/`sysop`/`util-dev`/`verifier`/`reviewer`
  шире проектных и формально затирают секретные deny — вопрос единообразия,
  не блокирующий чтение.

## INC-9 — работа умерших сессий копилась в stash и терялась (13 stash'ей)

- **Symptom (basis: quoted, Рудра):** «найди способ закоммитить и сделай
  системным так как владельцев некоторых старый изменений уже нет, если этого
  не решить сейчас, мусор ни куда не уйдёт».
- **Repro:** `git stash list` → 13 записей за 2026-09-29…2026-10-11 от веток
  `task/next-20261011-1445`, `task/shim-v3-hybrid`, `task/model-watch-1008`,
  `task/post-opus-transport`, `task/maya-lint-handshake`, `task/stow-reload`,
  `task/opencode-websearch` и др. — владельцев-сессий нет.
- **Root cause:** stash использовался как архив/очередь («вернуть потом»),
  инварианта жизни stash не было: умершая сессия = содержимое висит вечно,
  часть — уже утрачена (спека `newapi-provider-onboarding.md` жила только в
  untracked-дереве stash'а, jev-декларация `opencode.jsonc`, flush-запись
  `decisions.md` за 2026-09-29, сломанный алиас `to-serp`).
- **Fix:** спасение всех 13 пофайльовой классификацией против HEAD
  (уже в HEAD / отменено решениями / уникально) → 9 коммитов с пометкой
  «спасено из stash@{N}» → drop всех. Секрет-скан чисто. Системное
  закрепление: `AGENTS.md` § tree-hygiene п.8 + **ADR-027** (инвариант:
  stash без живого владельца не переживает конец сессии; 5-шаговое
  штатное спасение перед drop).
- **Evidence:** контрольная сверка 10/10 позиций OK; `git stash list` пуст;
  коммиты `4f6adfa`, `a354f13`, `0c31d08`, `bda69a9`, `34cb9ab`, `8b1f38b`,
  `373806e`, `89f240f`, `5f37592`, `f592560` (tg-bridge без владельца —
  приказ Рудры).
- **Отклонено:** `git stash clear` механически (унёс бы спасаемое наравне с
  мусором); восстановление из dangling-объектов (поздно и ненадёжно).
- **Status:** closed; residual — горячий WIP живых сессий паркуется
  `stash-foreign` и возвращается `pop` (штатный механизм tree-cop).

---

## INC-10 — CopyQ: «исчезающие» записи буфера; ложная тревога «утечки паролей»

- **Symptom (basis: quoted, Рудра):** после копирования длинного текста в окне
  CopyQ появились и сами исчезли 5–6 записей из символов, похожих на пароли
  (одинаковой длины); заподозрена утечка паролей.
- **Repro:** скопировать в буфер длинный текст (~17 КБ); параллельно в CopyQ видно
  несколько коротких записей из `[A-Za-z0-9]` одинаковой длины; через десятки
  секунд они пропадают сами, без действий; в логе CopyQ — ошибки чтения
  несуществующих файлов данных записи.
- **Root cause (факт):** баг CopyQ «мёртвого индекса» — запись держится в индексе,
  а её файл данных отсутствует; на чтении лог пишет
  `Failed to read file … .dat: Файл или каталог не существует` и роняет запись из
  списка. Повтор **ежедневно ~23:40–23:45** (серии за 10-04…10-06 и 10-10, один и
  тот же «мёртвый» id). Это и есть механика «появились → исчезли».
- **Root cause (гипотеза, не подтверждена):** часть записей была транзитной —
  CopyQ не сохраняет на диск элементы, помеченные источником как secret
  (`x-kde-passwordManagerHint`) либо иначе невалидные; потому в персистентном
  хранилище их нет и восстановить нечего.
- **Опровергнуто (важно):** **это не пароли.** Совпадающий по формату токен
  `buxrrn8Mou2VJH` (14 симв. `[A-Za-z0-9]`) встречается в системе ровно один раз —
  как **заголовок окна** в логе X-сессии; прочие вхождения — артефакты самого
  поиска (команды расследования в логах/БД opencode). Формат совпадает с
  идентификаторами opencode: у ~1400 id в хранилище shell-выводов суффикс ровно
  14 base62 — единая длина есть подпись генератора id. Секретов в хранилище
  CopyQ нет: высокоточный скан (PGP/JWT/AWS/`ghp_`/`sk-`/`xox`/`password=`) — 0;
  менеджеры паролей не установлены; маркеров `passwordManagerHint` нет; `~` = 700 →
  буфер недоступен другим пользователям системы.
- **Fix/workaround:** сторонний харнес — не патчим (workaround + запись-факт +
  майнинг апстрима). Объём для мастерской: A) ремонт индекса/чистка «мёртвых»
  ссылок — точечно; B) харденинг конфига CopyQ (`dotfiles/copyq/.config/copyq/`:
  игнор secret-элементов, лимит истории, опц. шифрование — GnuPG-плагин уже есть)
  `[проверить: точное имя опции ignore-secret в CopyQ 16]`; C) диагностика
  устойчивой воспроизводимости. Дизайн-требующий пункт — задача с ID (`proposed`).
- **Evidence:** `docs/handoffs/2026-10-13-copyq-clipboard-vanish-incident.md`
  (развёрнутая запись BF-20261013-01); app-лог CopyQ — серии `Failed to read file
  … .dat` ежедневно ~23:40–23:45; X-session лог — `current-title: [<14-base62> — CopyQ]`;
  хранилище CopyQ — персистентно ~31 запись, секретов 0.
- **Status:** `open` (передано в мастерскую; если ремонт индекса не окончателен —
  завести отдельную задачу с ID).

## INC-11 — decision-queue-hook: false-positive карточки на allow-события + NUL-коррупция

- **Symptom:** в `OpenCode-Vault/control-plane/decision-queue/cards/` появляются карточки с `title: "Permission request"`, `status: "pending"` на КАЖДОЕ evaluate-событие, включая `effect: allow` (примеры: `2026-10-13-102150-{external-directory,shell}.json`, `2026-10-13-102207-{read,grep}.json`). Наблюдатель очереди принимает shadow-шум за живой ask → ложный рапорт «агент заблокирован пермишенами» (потрачен багфикс-цикл на несуществующую проблему). Дополнительно: `2026-10-13-102207-grep.json` бит — хвост из NUL-байтов, `jq: Invalid numeric literal at line 26`.
- **Repro:** запуск любого субагента с read/grep → permission evaluate с effect allow → карточка pending в волте.
- **Root cause:** плагин `decision-queue-hook.ts` (global) пишет карточку на каждое событие независимо от effect — нет фильтра `effect === "ask"`; записи не атомарны (гонка writer'ов → NUL-хвост).
- **Fix (предложение):** фильтровать только ask-события; атомарная запись (temp+rename); allow-события не создавать (или отдельный журнал без статуса pending).
- **Evidence:** диагноз мета-агента (сессия ses_ecbd5c45fffeXaz33p2JtXZicR, 2026-10-13): DB `session_v2.permission` пуст, config-слои чисты, hook `evaluate` не мутирует effect; битая карточка подтверждена jq.
- **Status:** OPEN — на разбор Мастерской. (Тикет от сессии «Централизация», ses_eceb23a71ffeJO9QnFou8VngZC.)

## INC-12 — delivery-check не видит письма, доставленные через `opencode run`

- **Symptom:** письмо отправлено по канону peer-comms (`opencode run -s <ses> -m <model> "$(cat file)"`), ответ адресата получен, journal фиксирует `sent` (`receipts-out.jsonl`: `f47d2d01aa07ee23-20261013-…`), но `tools/peer-comms/delivery-check.sh <ses> <substring>` отвечает `NOT-DELIVERED: … (за 7 дней)`.
- **Repro:** отправить письмо через `opencode run` в сессию-адресата, затем delivery-check по подстроке ответа → NOT-DELIVERED при фактической доставке.
- **Root cause (гипотеза):** delivery-check ищет в хранилище одного канала (mail-storage letter.sh), а письма `opencode run` попадают в сообщения сессии адресата (session message API) — расхождение каналов проверки и доставки.
- **Fix (предложение):** delivery-check должен читать messages сессии адресата (`GET /api/session/{id}/message` или storage) либо оба канала; задокументировать в `02-Methods/peer-comms.md` (OpenCode-Vault), какой канал чем проверяется.
- **Evidence:** вывод сессии sysop/dotfiles 2026-10-13 (RECEIPT sent + NOT-DELIVERED на доставленное письмо; тест §4 пройден по содержанию).
- **Status:** OPEN — на разбор Мастерской. (Тикет от сессии «Централизация».)
