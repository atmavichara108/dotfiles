---
kind: contract
title: Bugfix-плагин v1 — проактивный capture сбоев и routing в named fix-исполнителей
spec-home: dotfiles/docs/specs/
date: 2026-10-07
status: approved — approval Рудры 2026-10-14 («включай»); runtime разрешён и работает: bugfix-capture.ts (Phase 1–3) в global plugins + /bugfix; reviewer CLEAR, verifier PASS 2026-10-14
owner: sysop (route: dotfiles primary/sysop; fallback UNROUTABLE, не general)
basis: 02-Methods/incident-fix (vault: Route-таблица, форма записи инцидента);
       04-Memory/route-log/2026-10-06-bugfix-logging-research.md; 06-Audits/
       2026-10-06-team-letter-protocol-and-bugfix-research-draft.md (§4–5, П.3
       «классификаторы — точечно, не сейчас»); docs/specs/mailing-protocol-proto.md
       (double-ack / read-gate); docs/specs/done/peer-comms-handshake.md (hello/
       ping/bye/find); глобальный AGENTS.md «Сбои — на багфикс на лету»
mandate: Рудра (через Дирижёра), 2026-10-07 — «спека для будущего проактивного
         Bugfix-плагина; plugin в этом поручении не реализовывать; scope ровно
         один новый spec-файл»
---

# Bugfix-плагин v1 — execution spec (draft)

## S1. Проблема

Сбои фиксируются вручную (инцидент-записи в handoff/память по §incident-fix),
и теряются в трёх местах: (а) сбой, который агент «проглотил» и обошёл, не
попадает ни в один лог; (б) повтор одного и того же сбоя в разных сессиях не
группируется и не виден координатору; (в) маршрут на named fix-исполнителя
выбирается «в голове» агента, а не детерминированно. Решение Рудры: все сбои
и обходы фиксируются и маршрутизируются в bugfix-процесс — без LLM в цикле и
без расширения прав плагина.

## S2. Что требуется (high-level)

OpenCode V2-плагин (dotfiles-домен; канон в
`opencode-global/.config/opencode/plugins/`, после stow —
`~/.config/opencode/plugins/`), который:

1. **слушает** события (S3) и детерминированно собирает metadata-only записи;
2. **классифицирует** по конечному словарю error-class — сопоставлением строк/
   кодов, без LLM (S5);
3. **группирует повторы** (дедуп по correlation-id в окне) — счётчик, а не
   независимые инциденты (S4);
4. **создаёт локальный metadata-сигнал** с рекомендуемым именованным
   fix-route по таблице (S6); сам не уведомляет Дирижёра и не пишет в проект;
5. **не создаёт project incident/handoff-файлы.** Их создаёт primary workflow
   после проверки сигнала по форме §incident-fix. Listener фиксирует только
   обнаружение — не «fix» и не ownership transfer;
6. **не правит код, не вызывает task, не запускает subagent'ов и LLM.**

## S3. Источники события (кандидаты, не runtime-гарантия)

Эта таблица описывает желаемое покрытие, а не утверждает наличие всех hooks в
OpenCode V2. До реализации каждый кандидат сверяется с установленными типами и
реальным payload; неподтверждённый источник остаётся gap, не PASS.

| Класс | V2-кандидат и наблюдаемое поле | Состояние / fallback |
|---|---|---|
| tool failure | `ctx.tool.hook(...)` candidate; tool name + result/error fields | не подтверждён для всех failure-классов; primary фиксирует видимый результат |
| provider/quota/timeout | provider API event | hook/payload не подтверждены; failed dispatch видит primary |
| permission | `ctx.permission.hook("evaluate")` или stream `permission.asked`/`permission.replied`; только action/effect/source metadata | частично представлен в соседних плагинах; соответствие каждому отказу verifier проверяет по факту |
| session timeout | `session.idle` несёт `sessionID`, но не причину timeout | timeout не выводить из idle; primary фиксирует только реально наблюдаемое |
| peer-comms receipts | `letter.sh` receipts + `delivery-check.sh` read-gate | plugin hook/polling не заявлен; receipts проверяет primary workflow |
| мягкий сбой / wrong-result | нет детерминированного события | только явный report пользователем/primary; автоматическое покрытие не обещается |

Для каждого включаемого источника acceptance фиксирует точные V2 hook/event,
payload, fixture и ограничения. Если hook недоступен или shape расходится,
источник исключается из listener coverage, а primary обязан fail-visible
обработать известный сбой по BF-20261010-01. Healthy вызовы не создают incident.

## S4. Модель записи (djsonl)

Локальный capture ledger: `~/.local/state/opencode/incidents/<project>.djsonl`
(append-only, строка = metadata event) + агрегат `incidents-index.jsonl`
(группировка повторов). Это только сигнал плагина, не project incident или
handoff; primary создаёт такие артефакты отдельно после проверки сигнала.

Плагин вправе записать только capture-поля:

```
capture_id (opaque ID)       ts (epoch)
error_class (S5 enum)        source_class (fixed enum)
session_id (validated ID)    project_slug (ALLOWED_REPOS enum)
safe_hint (fixed enum)       count / first_ts / last_ts
recommended_route (S6 enum)
```

`status`, `route_state`, `notification_state` и `notification_flag` принадлежат
primary workflow и записываются только в project incident/handoff после проверки
сигнала. Они не входят в capture ledger и не заполняются listener'ом.
`status` имеет enum `open|reported|dispatch|fixed|rejected|deferred`; `dispatch`
значит, что именованный исполнитель принял маршрут, не что фикс завершён.
`route_state: ready|blocked|unknown` отражает доступность маршрута.
`notification_state: not_required|pending|sent|started|finished|cannot|unknown`
принадлежит B18 workflow. `notification_flag=deferred-after-B9` — только метка
отложенного уведомления, не incident status.

- **correlation_id** для дедупликации собирается из `project_slug`,
  `error_class` и `safe_hint` только после allowlist-проверок; сам hint — значение
  фиксированного словаря, например `verifier-provider-451`,
  `peer-write-self-echo`, `stale-status-claim`, `shell-quote-bug`;
- B18 transport rc не является notification state: `delivery-check.sh` rc 0/1/2
  — результат команды; только отсутствие `started` после deadline переводит
  workflow notification state в `unknown`. Тот же `message_id` не отправляется повторно;
- классификация размера: tiny (однострочная точечная), medium (локальная
  правка), design (требует решения — становится задачей с ID);
- ротация: файл >1 МБ или >5000 записей → `_archive/`; решённые баги не
  удаляются, архивируются.

## S5. Классификация (детерминированная, без LLM)

Словарь error_class по паре (source, pattern):

```
tool-fail             — нулевой exit не получен от tool
provider-unavailable  — «model unavailable» / provider сообщает unavailable
provider-quota        — quota/balance exhausted
provider-timeout      — hang/таймаут апстрима
permission-blocked    — отказ permissions-гейта (ask без выдачи)
peer-write-timeout    — write-channel: ack не пришёл в окне
peer-self-echo        — ответ соседа совпал с текстом отправителя (свой же ход)
stale-status-claim    — «статус выдан как прогресс», не подтверждённый диском
shell-quote-bug       — unmatched quote/heredoc при передаче текста письмом
model-overwrite       — runtime-смена модели адресата в write-канале (не
                        фронтматтер-пины model: — они шум по AGENTS.md)
unknown               — fallback-класс, не попал ни в один патерн
```

Патерн-таблица — константы плагина, переиспользуются в тестах; пополнение
только по мандату после 3+ реальных срабатываний (решение Рудры: классификаторы
— точечно, не в этом мандате).

## S6. Route recommendation (named fix-route, без LLM)

Фиксированная таблица-рекомендация (никакого auto-dispatch):

| error_class | recommended fix_route |
|---|---|
| tool-fail | named executor зоны виновного инструмента (bash-dev / util-dev / stow-ops) |
| provider-unavailable / provider-quota / provider-timeout | workflow применяет актуальное правило retry/лимит из orchestration; затем STOP и рапорт |
| permission-blocked | meta (обновление permissions), затем рестарт сессии |
| peer-write-timeout / peer-self-echo | фикс peer-comms-инструментов (bash-dev); discovery-канон по fe66edd уже покрывает часть |
| stale-status-claim | sysop — немедленное устранение (workflow-гейт), не Дирижёр |
| shell-quote-bug | bash-dev (канон: текст письма в файл, вызов через `$(cat файл)`) |
| model-overwrite | рекомендация primary выставить `notification_flag=deferred-after-B9` в project incident; capture ledger этот workflow-флаг не содержит |
| unknown | sysop — рапорт, route не выбран |

Плагин не шлёт письма и не создаёт проектный handoff. Он пишет только локальный
metadata signal. Primary проверяет сигнал, выбирает маршрут и создаёт
incident/handoff. При отсутствии active `bugfix` claim primary выставляет
`route_state=blocked`, сохраняет инцидент/handoff или останавливает orchestration
с `BLOCKED`; fallback на `general` запрещён (см. BF-20261010-01 §5).

## S7. Redaction & Scope Guard

1. До записи применяется fail-closed проверка ко всем исходным и производным
   полям. Если secret/path detector сработал или проверка упала — запись НЕ
   создаётся; лог содержит только код отказа, без совпавшего фрагмента.
2. Prompts, LLM-ответы, полные tool outputs, произвольный stderr, команды и
   абсолютные пути никогда не записываются. Исключения по длине не делают
   свободный текст безопасным.
3. `symptom` и `repro_hint` — только enum/шаблон из кода; `evidence_ref` —
   непрозрачный ID, без пути или содержимого. Для каждого поля есть fixtures
   на секреты, credential-like substrings и path traversal.
4. Не логировать сырые exception/error text: только error class и безопасный
   числовой код, если его поле подтверждено API.
5. Scope Guard: запись создаётся только для `project` из константы
   `ALLOWED_REPOS` (dotfiles + проекты Рудры). Репо вне списка — запись не
   создаётся, в stderr плагина — метка NO_CREATE (никакого молчаливого
   подавления).

## S8. «Не баг, а фича» (обязательный шаг после подтверждённого fix)

После verifier PASS на фикс — плагин предлагает (не решает) оценку
«полезного использования бага» (research §4, шаг 5-в-incident-fix):

```
has-feature-potential: true | false
feature-evidence (одна строка, ≤150 символов)
```

false — нормальный ответ (если фикс исчерпал вопрос); не форсируем. Пример:
сбой peer-comms self-echo дал фикс discovery (fe66edd), из которого выросла
`find --role` как фича-обёртка handshake-реестра.

## S9. Double-ack / read-gate (интерфейс primary с B18)

Канон: `docs/specs/mailing-protocol-proto.md` (B18 materialized) и
`docs/specs/done/peer-comms-handshake.md` S7. Плагин не читает receipts,
не опрашивает state и не отправляет письма: B18 выполняет primary workflow
через `tools/peer-comms/letter.sh` и `delivery-check.sh`.

1. `letter.sh` пишет `sent{message_id, digest, ts}` в receipts; metadata signal
   плагина не считается `sent` и не подтверждает доставку;
2. read-gate: получатель пишет `started` при первом контакте без оценки
   качества — это «сообщение прочитано»;
3. double-ack: `finished` обязателен с артефакт-ссылкой (SHA, путь);
   `cannot` допустим с одним конкретным блокером — не штраф;
4. `delivery-check.sh` rc=0/1/2 означает соответственно доставлено / пока не
   доставлено / ошибка проверки. Это не notification state. Только отсутствие
   `started` после deadline переводит notification state в `unknown`, не
   `failed`; повторная отправка того же `message_id` запрещена. Новое письмо
   требует нового ID и отдельного решения primary;
5. receipts — только метаданные (id/digest/ts/scope/session), без тела письма
   (тело — секрет, чат; сверки digest).
6. Канонический state-path: `~/.local/state/opencode/mail/` (см. B18).

## S10. Обязательные кейсы (capture-тесты)

Порядок: текстовая спека → reviewer → verifier → отдельный approval → реализация
(Phase 1: только подтверждённые capture источники + rotation; Phase 2: primary
workflow route/notify; Phase 3: B18 ack/receipts). Каждый шаг имеет собственный
scope и verifier-gate; текущее одобрение содержания не разрешает runtime-код.

### Кейс 1 (peer-write-timeout / receipts)
Это workflow/read-gate кейс, не listener hook. Primary вызывает
`delivery-check.sh`; rc=0/1/2 трактуются только как результат проверки. Если
после deadline нет `started`, primary фиксирует notification state `unknown`,
не повторяет прежний `message_id`, а создаёт безопасный handoff либо после
проверки риска дубля инициирует новое письмо с новым ID. Изменение модели
адресата не является поводом молча переопределять model или обходить B18.

### Кейс 2 (provider unavailable/quota/hang)
Fixtures отдельно покрывают provider unavailable, quota/balance и timeout.
Provider hook пока не подтверждён; до доказательства конкретного V2 payload
эти сбои фиксирует primary при failed dispatch. Listener не заявляет автоматический
capture и не инициирует retry; лимит повторов берётся из действующего orchestration
контракта, затем STOP и отчёт.

### Кейс 3 (stale-status claim; workflow-only)
Симптом: старый статус (например устаревший PASS из собственной истории)
подан как текущая информация — сверяющий видит «done» по записи, хотя диск
это не подтверждает. Подтверждённого session hook для проверки истины по диску
нет. Primary сверяет «статус ↔ факт на диске» и при расхождении создаёт incident;
плагин не выводит stale-status из текста сессии.

### Кейс 4 (shell-quote bug)
Fixture может проверить классификатор на безопасном коде/enum, но автоматический
перехват `tool.execute.after` остаётся `[не подтверждён]`. Пока hook/payload не
подтверждён, primary отмечает этот сбой workflow-путём; сырая команда в запись
не попадает.

### Split: immediate vs deferred-after-B9

> **B9** — позицию бэклога Дирижёра (очередь именных мандатов, ведётся вне
> этого репо; в репо B9 не определён — ссылка именная). Тема B9 —
> model-overwrite (правки pinned-моделей в агентских конфигах). Отлагание
> снимается Дирижёром при закрытии B9.

- immediate: stale-status-claim (Кейс 3) — workflow-only сверка
  «статус ↔ факт на диске» primary;
- deferred-after-B9: model-overwrite получает `notification_flag=deferred-after-B9`
  только если источник capture подтверждён. Это не incident status и не скрывает
  инцидент; до закрытия B9 уведомление не отправляется.

## S11. Sustainability-фильтр (обязательный чек)

| Фильтр | Как выполняется |
|---|---|
| не грузим машину | только подтверждённые hooks, без фоновых процессов; no daemon, no cron |
| не раздуваем контекст | логи — append-only в state (в контекст сессии НЕ попадают); Дирижёру — краткий сводный блок не более 5 строк |
| токеномика | zero-LLM в capture/группировке/уведомлении; только патерны |

## S12. Acceptance (что доказывает реализатор перед приёмкой)

smoke (fixtures, реальные запуски, без LLM):

1. tool-fail capture — только если соответствующий V2 hook/payload подтверждён;
   иначе fixture проверяет primary workflow fallback. Запись содержит только
   safe enums/metadata, не stderr.
2. secret-leak guard — fake secret (`token=foo`) во всех исходных и производных
   полях → fail-closed без значения и записи; отдельно проверить secret в
   exception/error path, не допуская сырого текста в stderr/runtime logs.
3. detector failure — secret/path detector бросает исключение/возвращает ошибку:
   запись не создаётся, наружу уходит только фиксированный код отказа, без
   исходного значения и текста исключения.
4. dedup — дважды одинаковый сбой → одна запись count=2.
5. correlation — одинаковый error_class+hint в разных сессиях → склейка по
   correlation_id в агрегате (не отдельные записи).
6. Scope Guard — project вне ALLOWED_REPOS → запись не создаётся, NO_CREATE.
7. Route-table: error_class → fix_route детерминировано (fixture-набор).
8. zero-LLM: grep-аудит (без LLM-вызовов/провайдерских функций).
9. B18 workflow: реальные `letter.sh`/`delivery-check.sh` receipts, rc=0/1/2,
   deadline→unknown, no-resend того же ID; плагин сам receipts не читает.
10. Для каждого S3 source — hook/API + payload evidence либо пометка
   unsupported и доказанный workflow fallback; не засчитывать фиктивное покрытие.
11. При отсутствии active `bugfix` claim `route_state=blocked`; primary создаёт
    handoff/incident или возвращает `BLOCKED` для дальнейшей orchestration, не
    блокируя исходный tool.

Реализация + verifier PASS = обязательное условие ко каждому шагу Phase 1–3;
не меняем словарь maya-lint, release-пайпы, чужие репо.

## S13. Rollback / disable

- env-флаг `BUGFIX_PLUGIN=off` — плагин полностью пассивен (fail-closed).
- Никаких внедрений в pre-commit/часы и никаких exit-кодов, ломающих релиз;
  записи всегда metadata-only; сбой capture сам не повышает приоритет.
- Disable listener не снимает fail-visible обязанность primary из
  `bugfix-failure-rule.md`: известный сбой получает безопасную запись/handoff
  либо явный BLOCKED дальнейшей orchestration; штатный инструмент не блокируется,
  но silent continuation запрещён.
- Откат — revert коммита плагина; state-файлы остаются (метаданные безопасны).

## S14. Route management

- Таблица S6 — рекомендация для sysop/Дирижёра; никаких auto-dispatch.
- Fallback UNROUTABLE (не general): невыводенный fix-исполнитель → sysop
  рапорт, не молча. Silent fallback запрещён.

## S15. Что НЕ в этой спеки

- реализация/код/dispatch pipeline, LLM-классификаторы (точечно, не сейчас —
  решение Рудры), auto-enable «не баг, а фича»;
- словарь maya-lint (владелец librarian); provider/permission-фиксы (отдельный
  мандат);
- модельные правки (model-overwrite — deferred-after-B9).

Фазы: Phase 1 = capture(S3–S7); Phase 2 = route+notify (S6, S8–S9);
Phase 3 = ack/receipts-conform (S9).

## S16. Deliverables (после approval, отдельный мандат)

1. Плагин (dotfiles-зона `opencode`, имя `bugfix-capture.ts` — кандидат);
2. Тесты/fixtures (событийные заглушки, без LLM);
3. Запись в docs/decisions.md (ADR-021 — проактивный capture сбоев; ADR-020
   занят handshake);
4. Строка в AGENTS-кратках для агентов (как читать capture-логи).

## Открытые вопросы

1. `ALLOWED_REPOS` — точный состав (те же 8 репо, что в maya-lint dry-run)?
2. Уведомление Дирижёру: handoff-файл (append, приоритет) или живое письмо в
   peer-comms (после B9)?
3. Retention state-файлов: рекомендация 90 дней + архив _archive/.
4. XP/метатокены — кандидаты из отдельного черновика igraphv2; в эту спеку
   не включаются (свой мандат).

## Резолюции по открытым вопросам (решение Рудры, 2026-10-07)

1. `ALLOWED_REPOS` = те же 8 репо, что в maya-lint dry-run: dotfiles, OpenCode-Vault,
   AndroidOS, ChaT, recruiting-hr, dv-hub, SERPlux, TradingMind — фиксированный
   список-константа плагина, не вычисляется.
2. Уведомление Дирижёру — handoff-файл (append) как приоритет; живое письмо в
   peer-comms только когда нужен ответ в той же итерации.
3. Retention state-файлов: 90 дней + перенос в `_archive/`; секреты не архивируются.
4. XP/метатокены — вне этой спеки (фаза 4, отдельный мандат igraphv2).

Резолюция Рудры 2026-10-07 одобрила substance/направление текста, не реализацию.
Текущий статус остаётся `draft`; runtime-код запрещён до reviewer → verifier
PASS по этой ревизии и отдельного явного approval Рудры. После этого каждая
Phase 1–3 всё равно требует собственного scope и verifier-гейта.
