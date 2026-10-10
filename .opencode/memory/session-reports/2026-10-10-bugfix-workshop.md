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
- **Fix/workaround:** чужой harness (ядро OpenCode) не патчим. Workaround —
  открывать verifier-сессию сразу в целевом worktree, а не переносить рабочую.
  Прямую правку БД сессий не делать.
- **Evidence:** установлена v2.0.26; целевые каталоги существуют и доступны;
  живой перенос на рабочей сессии не повторялся. Источники: v2.0.26
  `session/move.ts`, `tool/plugin/opencode.ts`.
- **Status:** core-bug OpenCode, dotfiles-фикса нет; workaround `[проверить]`.

---

## Процессный урок (peer-comms)

Получив баг-хэндофф, primary обязан по протоколу писем (B18) слать `started`
при получении и `finished` при завершении через `tools/peer-comms/letter.sh`
(без `-m`, идемпотентно по message_id). В этой сессии баги пришли прямым прометом
(не через канонический журнал — в `receipts-out.jsonl` входящего на сессию нет),
поэтому формальная квитанция не ушла. Урок: при живом канале закрывать петлю
`started/finished`, если известен session_id отправителя и message_id (`--ref`).
