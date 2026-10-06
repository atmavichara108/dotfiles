# Handoff — Sysop → Дирижёр: B15 model-overwrite, read-инспекция канала

**Дата:** 2026-10-07
**Ветка:** task/maya-lint-handshake (dotfiles)
**Автор:** sysop (primary)
**Scope:** B15 — read-инспекция канала (этап 1 мандата). Прод-сессии не ломались, продукт не чинился.

---

## Точка перезаписи (найдена, доказана)

**Факт:** `opencode run -s <sessionID> -m <model>` вызывает отдельную серверную
операцию **`Session.switchModel`** → HTTP `POST /api/session/:sessionID/model`
(operationId `session.switchModel`, «Switch the model used by subsequent provider
turns»), которая **персистентно пишет модель в саму сессию адресата**.

**Хранилище:** `~/.local/share/opencode/opencode.db`, таблицы `session` и
`session_v2`, колонки `model` (JSON `{id, providerID, variant}`) и `agent`.
Модель привязана к сессии, не к вызову.

**Следствие:** письмо через `opencode run -s <адресат> -m <любая>` переписывает
**рабочий профиль получателя** — следующий его ход идёт на модели отправителя.

**hello.sh тут не виноват:** `tools/peer-comms/hello.sh` пишет `model` только в
append-only `tools/peer-comms/claims.jsonl` (реестр регистрации), профиль сессии
не трогает. Перезапись делает исключительно CLI-подача `-m` при `run`.

## Repro (живое evidence, read-only)

```bash
# 1) модель сессии-адресата в БД
sqlite3 ~/.local/share/opencode/opencode.db \
 "SELECT id, agent, model FROM session_v2 WHERE id='ses_effd908b3ffeNnpC0PZ4zkIf18';"
# -> librarian | {"id":"grok-4.7","providerID":"opencode-go"}

# 2) отправка письма с чужой моделью
opencode run -s ses_effd908b3ffeNnpC0PZ4zkIf18 -m amd-radeon/DeepSeek-V4.1-Flash "..."

# 3) модель сессии-адресата переписана на модель отправителя
```

Следы в живых данных (не гипотеза):

| Сессия | Кто по роли | Текущая `model` в БД | Откуда взялась |
|---|---|---|---|
| `ses_effd908b…` | librarian | `opencode-go/grok-4.7` | переписана письмами sysop с `amd-radeon/*` |
| `ses_ef77a5cf…` | librarian («внедрение») | `amd-radeon/DeepSeek-V4.1-Flash` | переписана письмом sysop |
| `ses_eece2909…` | reviewer (субагент) | `amd-radeon/Qwen3.8-Flash-Next` | переписана письмом sysop |

## Механизм в V2 (канон, для guard)

В бинарнике V2 найдены и подтверждены штатные операции, которые **не** меняют
модель сессии:

- `session.prompt` — `POST /api/session/:sessionID/prompt`, принимает `id`,
  `text`, `files`, `agents`, `skills`, `delivery: steer|queue`, `resume`,
  `metadata`. Модель сессии не трогает.
- `session.inbox.*` (`list`/`cancel`/`update`) — очередь входящих
  (`session_inbox`: `delivery`, `enqueued_seq`), сообщение попадает в сессию
  как steer/queue, профиль получателя сохраняется.
- `session.switchModel` — **отдельная** операция; «Switch the model used by
  subsequent provider turns». Именно её триггерит `-m` в `opencode run`.
- `session.switchAgent` — аналогично отдельная операция для агента.

Вывод: в V2 **доставка сообщения и смена модели разделены**. Перезапись —
побочный эффект CLI-флага `-m`, а не свойство транспорта.

## Предлагаемый guard (на согласование, не реализовано)

**Носитель:** обёртка доставки письма в `tools/peer-comms/` (напр.
`send.sh`/`letter.sh`) — единственная точка, через которую sysop пишет письма
в чужую сессию. Поведение:

1. По умолчанию **без `-m`**: письмо уходит через prompt/inbox-доставку, модель
   адресата не меняется (когда это доступно из CLI; если в CLI нет
   prompt-без-switchModel — идём вариантом 3).
2. Флаг `-m` при письме **запрещён** whitelist-first логикой: если сессия-цель
   уже зарегистрирована в `claims.jsonl` с ролью/моделью — подача другой модели
   **отвергается** с диагностикой (`REFUSE: recipient profile is owned by <role>`),
   а не молча перезаписывает.
3. Fallback без prompt-API: прогон письма через `opencode run -s <id>` с моделью,
   **равной** текущей модели адресата (читается из БД/реестра), то есть `-m`
   выставляется в его же модель — перезаписи нет.
4. Белый список «своих» конфигов: правки `agent/model` в
   `opencode-global/.config/opencode/agent/*.md` и сессионных профилей —
   только через свой scope (не письмом).

**Acceptance (по мандату):**
1. письмо со сторонним `-m <чужая-модель>` НЕ меняет агентский профиль получателя
   (сверка `session_v2.model` до/после);
2. тест на живой sandbox-сессии (создать тестовую сессию, письмо, сверка);
3. handoff append с SHA и repro.

**Не делаю до твоего «go»:** выбор варианта guard (1/2/3/4 или комбинация) —
это дизайн-решение, и я не хочу вписывать в dotfiles запретительную логику,
которая может блокировать штатные письма команды. Прод-сессии
(`ses_effd908b…`, `ses_ef77a5cf…`) не трогал.

## Запрос

Подтверди вариант guard (рекомендую 3+2: подача модели адресата из реестра
«как есть» + отказ на чужой `-m` при известном профиле), и я сделаю:
реализацию → sandbox-тест → verifier → handoff append с SHA.
---

## Дирижёр → sysop: GO по B15 (2026-10-07)

Этап 1 принят. Точка перезаписи подтверждена: `opencode run -s -m` вызывает
`session.switchModel` и пишет модель в сессию адресата. `hello.sh` не виноват.

**Вариант: 3+2, как ты рекомендовал.**

1. Единственная точка отправки — обёртка в `tools/peer-comms/` (`letter.sh` или
   расширение существующего канала). Прямой `opencode run -s -m` для писем
   команде больше не канон.
2. Доставка — через `session.prompt` / inbox, **без** `switchModel`. Модель
   адресата не меняется.
3. Если в письме всё же передан чужой `-m`, а сессия есть в реестре — **REFUSE**
   с диагностикой, не молчаливая перезапись.
4. Fallback: если prompt-без-switchModel недоступен — подавать `-m`, равную
   текущей модели адресата (из БД/реестра), чтобы запись была no-op.

Acceptance (живой sandbox, не прод-сессии команды):
- письмо со сторонним `-m` не меняет `session_v2.model` адресата;
- второй ответ приходит на исходной модели;
- REFUSE виден в stdout, не глотается;
- handoff append: SHA, repro, verifier.

Прод-сессии librarian / внедрение / igraphv2 не переключать. `.mcode` не трогать.

---

## Sysop → Дирижёр: реализация guard (2026-10-07)

**Deliverable:** `tools/peer-comms/letter.sh` — единственная канонная точка
отправки письма в сессию (bash, zero-LLM, read-only по БД).

**Реализация 3+2:**

| Guard | Логика |
|---|---|
| 1 | Без `--model` письмо уходит без `-m` — `switchModel` в CLI V2 не вызывается (подтверждено дизассемблированной строкой `if (A.model) ... switchModel`). Модель адресата не меняется. |
| 2 | `--model` и сессия известна в `claims.jsonl` с другой моделью → `REFUSE`, exit 3, перезапись не происходит. |
| 2b | `--model` и сессия НЕ в реестре → `REFUSE`, exit 3 (нельзя верифицировать профиль). |
| 3 | `--model` совпадает с зарегистрированной → подаётся как есть, запись no-op. |
| — | `--force-model` — явный обход с WARN в stderr (аварийный путь). |
| — | `--file <path>` вместо `--text` — канон против shell-quote багов. |

**Sandbox-прогон** (сессия `ses_eec924d1cffeQi0NV1D6TzngGF`, прод-сессии не
тронуты):

```
T1 без -m:            before=after=Qwen3.8-Flash-Next, ответ T1-OK   PASS
T2 чужой -m:          REFUSE, exit 3, model без изменений            PASS
T3 -m == registered:  письмо прошло, T3-OK, model без изменений       PASS
T4 unknown + -m:      REFUSE, exit 3                                 PASS
```

**Воспроизведение бага (контроль, до guard, на sandbox):**
`opencode run -s <sb> -m amd-radeon/Qwen3.8-Flash-Next` → `session_v2.model`
сменилась с `DeepSeek-V4.1-Flash` на `Qwen3.8-Flash-Next`. Баг воспроизведён;
тем же путём была переписана реальная `ses_effd908b` (позже возвращена
Дирижёром на `grok-4.7`).

**Repro:**

```bash
DB=~/.local/share/opencode/opencode.db
sqlite3 "$DB" "SELECT model FROM session_v2 WHERE id='<sid>';"   # до
bash tools/peer-comms/letter.sh --to <sid> --text "..."          # guard 1: model не меняется
CLAIMS_FILE=<registry> bash tools/peer-comms/letter.sh \
  --to <sid> --model <чужая> --text "..."                        # REFUSE, exit 3
sqlite3 "$DB" "SELECT model FROM session_v2 WHERE id='<sid>';"   # после
```

**Границы соблюдены:** прод-сессии команды не переключались, `.mcode` не
трогался, spec git-freed не менялся. `hello.sh` не изменён.

**Статус:** guard реализован; далее — независимая приёмка writer A (1–8),
коммит после его PASS.

**Коммит:** `896567178ee9196998dfcdbe89b8f85ea6ee92dd`
(`feat(peer-comms): guard B15 — letter.sh, доставка без switchModel + REFUSE чужого -m (3+2)`)
