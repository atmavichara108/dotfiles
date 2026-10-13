---
kind: execution-spec
title: Программное правило «сбой → багфикс»
spec-home: dotfiles/docs/specs/
owner: sysop
date: 2026-10-10
status: reviewed — reviewer approve-with-nits + verifier PASS (9/9, 2026-10-13); ожидает approval Рудры; runtime реализация запрещена до него
task-id: BF-20261010-01
basis: quoted — приложенный Рудры файл `bugfix-extdir-and-rule-20261010.txt`
       (в сообщении назван BAGFIX-LETTER), 2026-10-10;
       02-Methods/incident-fix.md (OpenCode-Vault);
       docs/specs/bugfix-proactive-plugin.md (рабочая draft-спека, substance
       approved Рудрой 2026-10-07);
       docs/specs/mailing-protocol-proto.md (B18);
       docs/specs/done/peer-comms-handshake.md
---

# BF-20261010-01 — программное правило «сбой → багфикс»

## 1. Мандат и статус

Требование Рудры (basis: quoted): «как только возникают проблемы/сбои/дефекты —
автоматически на багфикс, письмом в сессию мастерской по канону»; enforcement
должен быть программным, «не только текст в AGENTS»; дизайн-требующая работа
остаётся `proposed` до approval Рудры.

Эта спека — proposal, не разрешение на runtime-код. Реализация начинается
только после reviewer → verifier PASS и отдельного approval Рудры. Не
ослабляет approval gates, запреты секретов или project ownership.

## 2. Цель

На инфраструктурном сбое система обязана создать видимый metadata-only incident,
поставить обязательный workflow gate для агента-primary и оставить проверяемый
статус: письмо должно быть отправлено в активную bugfix-сессию либо явно
зафиксировано `route_state=blocked` с handoff. Listener (capture-плагин) не
отправляет письмо и не dispatch-ит агента; это делает primary workflow. Сбой
нельзя молча проглотить, считать исправленным только из-за workaround или
переводить в `general`.

Программно обеспечиваются capture, видимый сигнал и append-only запись;
исполнение workflow-gate primary остаётся контрактного уровня (подтверждённого
V2-API на блокировку хода нет) — поверх обнаруживаемого сигнала, а не вместо
него.

## 3. События и цена

Ни один источник ниже не считается подтверждённым runtime-hook, пока он не
проверен на установленной версии OpenCode V2. Матрица — контракт покрытия, а
не утверждение, что API уже существует:

| Класс | Кандидатный источник | Состояние | Если hook недоступен |
|---|---|---|---|
| permission rejection, включая `external_directory` | permission hook/event | `[проверить]` | primary фиксирует отказ как видимый инцидент |
| tool/channel failure, timeout, schema/transport | tool result/event, включая exit code | `[проверить]` | primary фиксирует известный сбой; неизвестный — `unknown` |
| plugin/script exception, nonzero exit, load failure | plugin log / результат вызова инструмента | `[проверить]` | primary фиксирует ошибку по доступному результату |
| model/quota/upstream timeout | provider event/error | `[проверить]` | failed dispatch от primary; не выводить наличие provider-hook из текста ошибки |
| receipts/deadline peer-comms | B18 receipts + workflow read-gate | автоматическое событие не подтверждено; listener не опрашивает файлы | primary проверяет receipts через канонический read-gate |

Для каждого источника reviewer/verifier должны связать класс с конкретным
V2 hook/event, payload и fixture; если такого hook нет, класс остаётся
непокрытым listener'ом и обслуживается fail-visible шагом primary. Нельзя
объявлять покрытие по одному лишь имени события или по наличию записи в логе.

Capture использует только событие/код/имя инструмента и безопасные
классификаторы. Он не сохраняет prompt, ответ модели, полный tool output,
абсолютные пути, произвольные команды или значения, похожие на секреты.
Дедупликация — по корелляционному ключу плагин-спеки S4
(`project_slug` + `error_class` + `safe_hint`) в окне сессии; кросс-сессийная
склейка — по правилам S4. Capture не ждёт сеть/LLM, не повторяет неудачный вызов, не
блокирует штатный инструмент и не увеличивает стоимость выше самого сбоя.
Повторяющиеся ошибки агрегируются; неизвестный сбой виден как `unknown`, не
отбрасывается.

## 4. Incident record

Каноническая форма реестра:

`symptom → repro → root cause → fix/workaround → evidence → status`

Минимальные поля: incident/task ID, timestamp, error class, source/tool,
очищенный symptom, безопасный repro hint, root-cause hypothesis vs confirmed,
fix-route, evidence reference. `symptom` — короткая метка из фиксированного
словаря; `repro hint` — тип/код шага без сырой команды, текста или пути;
`evidence reference` — только непрозрачный ID либо проверенная ссылка
`repo=<slug> sha=<40 hex> path=<repo-relative-path>` после secret scan. Никаких
absolute/home paths, содержимого файла или сырых stderr в этих полях.

`status` имеет enum `open|reported|dispatch|fixed|rejected|deferred`.
`dispatch` означает, что именованный fix-route принят в работу; он не означает
`fixed`. Полный закрытый список переходов: `open → reported → dispatch → fixed`;
`open|reported → rejected|deferred`; `dispatch → open` (откат маршрута);
`fixed → open` (reopen, с новым symptom-событием). Любой иной переход запрещён;
fixture на невалидный переход — часть §8. Исправления и смена статуса
добавляются append-only событием.

Отдельные поля не смешиваются со статусом инцидента:
- `route_state: ready|blocked|unknown` — доступность адресата/маршрута;
- `notification_state: not_required|pending|sent|started|finished|cannot|unknown` —
  состояние одного B18-сообщения;
- `deferred-after-B9` — только отдельная метка отложенного уведомления, не
  значение `status`.

Enum из S4 (`docs/specs/bugfix-proactive-plugin.md`) обязателен для
машиночитаемых BF-записей; свободная форма статуса в
повествовательном реестре мастерской — не machine contract. Статусы самой
задачи (`proposed`, затем по решению Рудры) не являются incident status.
Источник истины для записи — проектный incident registry/handoff; runtime
state — только metadata.

## 5. Каноническая маршрутизация

1. Обязанность по письму — у агента-primary в обязательном workflow gate; capture
   listener только создаёт metadata event/сигнал по канону draft-спеки плагина
   (substance approved, S2) и сам ничего не отправляет.
2. Когда адресат доступен, primary workflow отправляет письмо только через
    `tools/peer-comms/letter.sh`, соблюдая B18: один `message_id`, `started` при
    получении, `finished` с artifact/SHA или один конкретный `cannot`;
    duplicate-send запрещён. `delivery-check.sh` возвращает коды процесса:
    `0` — доставлено, `1` — пока не доставлено, `2` — ошибка самой проверки;
    это не значения `notification_state`. Deadline квитанции — константа
    реализуемого workflow read-gate, фиксируется этой спекой: **600 с** от `sent`;
    это не timeout отправки `letter.sh` (≥360 с) и не TTL claims (30 мин);
    значение меняется только правкой этой спеки. Если после deadline `started`
    так и не подтверждён, workflow переводит уведомление в
    `notification_state=unknown`; `rc=2` сам по себе такого перехода не означает.
    При `unknown` повтор того же `message_id` запрещён. Primary делает
    append-only handoff без повторной отправки либо, после проверки риска дубля,
    начинает новое действие с новым `message_id` (id = hash тела + день + from,
    поэтому новое письмо обязано отличаться по телу — ссылкой на
    incident/handoff).
3. Получателя искать через `hello.sh find --role bugfix` (или утверждённый
   Рудры эквивалент); session ID нельзя угадывать или хардкодить без срока.
   Настоящая спека для канала «сбой → мастерская» замещает резолюцию 2
   draft-спеки `bugfix-proactive-plugin.md` (handoff-приоритет остаётся для
   канала «Дирижёр», письмо — обязано здесь).
4. Сейчас claims registry не показывает активную роль `bugfix`. До регистрации
    canonical bugfix-сессии автоматический адресат не определён. При отсутствии
    адресата (проверка `hello.sh find` rc≠0 — обязанность workflow, не
    capture-события) workflow gate primary закрывает ход
    с `BLOCKED: no active bugfix session` и append-only handoff/incident; silent
    fallback запрещён.
    Listener не является единственным носителем gate: если он выключен,
    сломан или не загружен, primary всё равно обязан fail-visible обработать
    замеченный сбой — создать безопасный incident/handoff либо остановить
    дальнейшую orchestration с `BLOCKED: incident persistence unavailable`.
    Это не блокирует исходный штатный инструмент и не разрешает молчаливо
    продолжить workflow.
5. Письмо содержит только безопасное краткое описание, ID и ссылку на incident
   record; не секреты/полный вывод.
6. Фикс исполняется именованным владельцем зоны по существующему маршруту;
   ни capture-плагин, ни письмо не запускают произвольный auto-dispatch или LLM.

## 6. Dotfiles UX (после approval реализации)

- Добавить шаблон incident record в dotfiles с указанной формой и маркировкой
  гипотез/подтверждённых фактов.
- Добавить `/bugfix` command для первичного разбора, выбора named fix-route,
  записи evidence и проверки статуса; не подменяет approval и verifier.
- Связать её с Vault-методом `02-Methods/incident-fix.md`, не копируя и не
  меняя Vault-файлы из dotfiles.

## 7. Enforcement proposal

Предпочтительный механизм — узкий OpenCode V2 plugin/listener на подтверждённых
событиях tool/permission/provider, который делает metadata capture и
обязательный visible route signal. Он не меняет решение permission gate,
не расширяет права, не повторяет команду, не редактирует файлы инцидента за
пользователя и не dispatch-ит агента самостоятельно. До выбора hooks и
подтверждения их event shape — `[проверить]`; если runtime не даёт надёжного
hook, fallback должен быть fail-visible workflow gate, а не фиктивное покрытие.

## 8. Acceptance и rollback

1. Для каждого класса матрицы §3 указан подтверждённый V2 hook/payload и fixture
    либо явно описан workflow-fallback. Каждое событие, покрытое listener,
    даёт ровно одну безопасную запись либо dedup-count, без prompt/output/secrets.
2. `external_directory` отказ и ошибочный skill/tool schema приводят к видимому
   incident и маршруту; `[проверить]` — реальное событие в OpenCode V2.
3. При отсутствии active `bugfix` claim выводится BLOCKED, а не ложное `sent`;
    при наличии тестового active claim проверяются `started` и `finished` либо
    один `cannot`, все коды `delivery-check.sh` (0/1/2), переход в
    `notification_state=unknown` только после deadline без `started`, запрет
    повтора того же `message_id` и append-only handoff/new-ID путь; receipts
    соответствуют B18.
4. Healthy tool call — no incident; инструмент не блокируется и не повторяется.
5. Zero-LLM capture, redaction, dedup, latency/overhead и restart/disable
   проверены реальным verifier-прогоном; числовые пороги latency/overhead
   фиксируются отдельным пунктом при approval реализации (до этого unverifiable
   — не считать критерий выполненным качественной оценкой).
6. Reviewer возвращает findings; только verifier выносит PASS/FAIL.
7. Rollback/выключение listener не отключает fail-visible обязанность primary:
    при выключенном listener workflow фиксирует замеченный сбой либо явно
    останавливает дальнейшую orchestration с BLOCKED, не блокируя штатный
    инструмент. Записанные metadata incidents не удалять.

## 9. Вне scope и blockers

- Изменение Vault `opencode.json` не входит в dotfiles edit scope. INC-5
  исправлен apply'ем рабочего дерева по отдельному мандату Рудры (2026-10-10,
  восстановление из `origin/main`); residual — conflict-check при merge
  отошедшей task-ветки Vault, чтобы не откатить `cac2a00`.
- Источник — вложение Рудры `bugfix-extdir-and-rule-20261010.txt`; архивная копия
  (секрет-скан пройден 2026-10-13):
  `docs/specs/basis/BF-20261010-01-bagfix-letter.txt`. Ключевая формулировка
  процитирована в §1; канонический полный текст — архивная копия. Полный текст
  не копируется в runtime logs.
- OpenCode core/tool API не патчить; runtime недоступность описывать как
  `[проверить]` с workaround.
- `system-ops` сохраняет существующую узкую external-directory область
  canonical bridge; этот high-risk boundary не расширять данным proposal.
- Не устанавливать/удалять пакеты, не менять `/etc`/сервисы, не включать
  `push --force`.
