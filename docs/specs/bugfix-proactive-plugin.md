---
kind: contract
title: Bugfix-плагин v1 — проактивный capture сбоев и routing в named fix-исполнителей
spec-home: dotfiles/docs/specs/
date: 2026-10-07
status: draft — черновик; реализация запрещена до reviewer→verifier и approval Рудры
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
4. **уведомляет Дирижёра** (librarian) — metadata-сигнал с рекомендуемым
   именованным fix-route по таблице (S6);
5. **открывает incident/handoff файл** (append-only) в зоне проекта с формой
   §incident-fix: symptom / repro / root-cause-гипотеза / evidence / статус.
   Плагин фиксирует только обнаружение — не «fix»;
6. **не правит код, не вызывает task, не запускает subagent'ов и LLM.**

## S3. Источники события (перехват)

| Источник | Что ловим | Сбор (metadata-only) |
|---|---|---|
| tool.execute.after | exit != 0; stderr-патерны (timeout, 451, ECONNREFUSED, EACCES, unmatched-quote); «мягкий сбой» = команда прошла, результат не тот | tool name, exit code, до 2 строк stderr (redacted), ts, session, project |
| provider/API | HTTP 4xx/5xx (включая 451), stream hang/timeout | provider id, response code, elapsed; без тела ответа |
| permission.ask | отказ или невыдача разрешения (агент запросил — не получил) | gate/plugin name, действие, решение |
| session | таймаут хода; отсутствие подтверждения письма (sent без started в окне) | session id адресата, elapsed, kind |
| write-channel | deadline истёк без ack → статус `unknown`; read-gate/double-ack | message_id, адресат, elapsed |

Запрещено в записи: prompts, секреты, полные tool outputs (см. S7).

## S4. Модель записи (djsonl)

Файлы: `~/.local/state/opencode/incidents/<project>.djsonl` (append-only,
строка = запись) + агрегат `incidents-index.jsonl` (группировка повторов).

Схема записи:

```
bug_id (short uuid)        correlation_id
ts (epoch)                 class: tiny | medium | design
error_class (S5)           status: open|reported|dispatch|fixed|rejected|deferred|deferred-after-B9
session (id)               task (id | none)
project (slug)             owner (named agent, если известен)
symptom (≤200 chars)       repro (≤300 chars, минимальная команда/шаги)
evidence (redacted head)   fix_route (рекомендация, S6)
count (повторы)            first_ts / last_ts
```

- **correlation_id** — обязателен (research §5): `project/error_class/hint`;
  hint — короткое имя сбоя, например `verifier-provider-451`,
  `peer-write-self-echo`, `stale-status-claim`, `shell-quote-bug`;
- классификация размера: tiny (однострочная точечная), medium (локальная
  правка), design (требует решения — становится задачей с ID);
- ротация: файл >1 МБ или >5000 записей → `_archive/`; решённые баги не
  удаляются, архивируются.

## S5. Классификация (детерминированная, без LLM)

Словарь error_class по паре (source, pattern):

```
tool-fail             — нулевой exit не получен от tool
provider-451          — HTTP 451 / «model unavailable»
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
| provider-451 / provider-timeout | повтор с моделью отправителя (≤2 повторов суммарно), затем STOP и рапорт |
| permission-blocked | meta (обновление permissions), затем рестарт сессии |
| peer-write-timeout / peer-self-echo | фикс peer-comms-инструментов (bash-dev); discovery-канон по fe66edd уже покрывает часть |
| stale-status-claim | sysop — немедленное устранение (workflow-гейт), не Дирижёр |
| shell-quote-bug | bash-dev (канон: текст письма в файл, вызов через `$(cat файл)`) |
| model-overwrite | capture с флагом `deferred-after-B9`; уведомление Дирижёру — после закрытия B9 (см. S10-split) |
| unknown | sysop — рапорт, route не выбран |

Уведомление Дирижёру: плагин не шлёт письма сам — пишет сигнал в handoff-файл
и (опционально, фаза 2) показывает сигнал в канале; Дирижёр берёт, когда хочет.

## S7. Redaction & Scope Guard

1. Патерны секретов (token/key/private/ssh/password и похожие) — если
   сработали: запись НЕ создаётся, FAIL-closed, строка с стоп-сигналом в лог
   плагина без содержимого.
2. Prompts, LLM-ответы, полные tool outputs — никогда не записываются.
3. Head stderr: ≤2 строк, ≤200 символов суммарно, после redaction.
4. Scope Guard: запись создаётся только для `project` из константы
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

## S9. Double-ack / read-gate (связь с mailing-protocol-proto)

Родительская спека: `docs/specs/mailing-protocol-proto.md` (автор igraphv2,
коммит f748ee1, proto-draft). Плагин не дублирует почтовую реализацию —
использует её события:

1. перед письмом Дирижёру — `sent{message_id, digest, ts}` в receipts;
2. read-gate: получатель пишет `started` при первом контакте без оценки
   качества — это «сообщение прочитано»;
3. double-ack: `finished` обязателен с артефакт-ссылкой (SHA, путь);
   `cannot` допустим с одним конкретным блокером — не штраф;
4. deadline истёк устойчиво: `unknown`, не «failed»; продление = новое
   письмо (новый message_id), повторная отправка того же message_id запрещена;
5. receipts — только метаданные (id/digest/ts/scope/session), без тела письма
   (тело — секрет, чат; сверки digest).
6. state-path: `~/.local/state/opencode/mail/` — рекомендация (финальное
   размещение — решается при реализации, не в этой спеке).

## S10. Обязательные кейсы (capture-тесты)

Порядок: спека → reviewer → verifier → approval → реализация (Phase 1:
capture + rotation; Phase 2: routing + notify; Phase 3: ack/receipts).

### Кейс 1 (peer-write-timeout / модель адресата изменена)
Симптом: письмо соседу отправлено, но окно ack истекло. Особый вариант:
адресат сменил модель (явный `--model` обязателен — модель отправителя, иначе
маршрутизация не гарантирована). repro:
`tools/peer-comms/hello.sh find --role librarian` — сосед stale. Плагин
ловит: sent без started в окне → запись peer-write-timeout.

### Кейс 2 (verifier provider 451/hang)
Симптом: verifier dispatch → HTTP 451, повтор с той же моделью — та же
ошибка; ход висит до таймаута. Причина: провайдер недоступен. Плагин ловит:
provider-451 через S3 provider слой; рекомендация — fallback повтор с
моделью отправителя (≤2) и STOP.

### Кейс 3 (stale-status claim)
Симптом: старый статус (например устаревший PASS из собственной истории)
подан как текущая информация — сверяющий видит «done» по записи, хотя диск
это не подтверждает. Плагин фиксирует через session-слой (S3).
Это немедленное устранение (не deferred): рабочий шаг — сверка «статус ↔
факт на диске» в workflow рапорта, не в плагине (см. S10-split).

### Кейс 4 (shell-quote bug)
Симптом: `zsh: unmatched "` при передаче текста с кавычками/скобками напрямую
в CLI-команде; ловится патерном S3 (tool.execute.after). fix_route bash-dev:
канон «текст письма в файл, вызов через `$(cat файл)`» (см. peer-comms).

### Split: immediate vs deferred-after-B9

> **B9** — позицию бэклога Дирижёра (очередь именных мандатов, ведётся вне
> этого репо; в репо B9 не определён — ссылка именная). Тема B9 —
> model-overwrite (правки pinned-моделей в агентских конфигах). Отлагание
> снимается Дирижёром при закрытии B9.

- immediate: stale-status-claim (Кейс 3) — устраняется рабочим шагом
  «статус ↔ факт на диске», capture остаётся в плагине;
- deferred-after-B9: класс model-overwrite — capture записывается, но
  уведомление Дирижёру откладывается до закрытия B9 (в записи флаг
  `deferred-after-B9`, умолчанной обработки нет).

## S11. Sustainability-фильтр (обязательный чек)

| Фильтр | Как выполняется |
|---|---|
| не грузим машину | 5 hook-событий listener без фоновых процессов; no daemon, no cron |
| не раздуваем контекст | логи — append-only в state (в контекст сессии НЕ попадают); Дирижёру — краткий сводный блок не более 5 строк |
| токеномика | zero-LLM в capture/группировке/уведомлении; только патерны |

## S12. Acceptance (что доказывает реализатор перед приёмкой)

smoke (fixtures, реальные запуски, без LLM):

1. tool-fail capture — форсед ненулевой exit tool → запись с correlation_id
   и head stderr (без full output).
2. secret-leak guard — fake secret (`token=foo`) в stderr → FAILED с
   stop-сигналом; никакой записи.
3. dedup — дважды одинаковый сбой → одна запись count=2.
4. correlation — одинаковый error_class+hint в разных сессиях → склейка по
   correlation_id в агрегате (не отдельные записи).
5. Scope Guard — project вне ALLOWED_REPOS → запись не создаётся, NO_CREATE.
6. Route-table: error_class → fix_route детерминировано (fixture-набор).
7. zero-LLM: grep-аудит (без LLM-вызовов/провайдерских функций).
8. double-ack/read-gate: по канонам mailing-protocol-proto.

Реализация + verifier PASS = обязательное условие ко каждому шагу Phase 1–3;
не меняем словарь maya-lint, release-пайпы, чужие репо.

## S13. Rollback / disable

- env-флаг `BUGFIX_PLUGIN=off` — плагин полностью пассивен (fail-closed).
- Никаких внедрений в pre-commit/часы и никаких exit-кодов, ломающих релиз;
  записи всегда metadata-only; сбой capture сам не повышает приоритет.
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

Статус спеки: draft → approved (Рудра, 2026-10-07); реализация — Phase 1–3 по
отдельным мандатам с verifier-гейтом на каждом шаге.
