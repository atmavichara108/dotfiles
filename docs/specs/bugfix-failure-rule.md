---
kind: execution-spec
title: Программное правило «сбой → багфикс»
spec-home: dotfiles/docs/specs/
date: 2026-10-10
status: proposed — runtime реализация запрещена до отдельного approval Рудры
task-id: BF-20261010-01
basis: quoted — приложенный Rudra файл `bugfix-extdir-and-rule-20261010.txt`
       (в сообщении назван BAGFIX-LETTER), 2026-10-10;
       02-Methods/incident-fix.md (OpenCode-Vault);
       docs/specs/bugfix-proactive-plugin.md (рабочая draft-спека, substance
       approved Рудрой 2026-10-07);
       docs/specs/mailing-protocol-proto.md (B18);
       docs/specs/done/peer-comms-handshake.md
---

# BF-20261010-01 — программное правило «сбой → багфикс»

## 1. Мандат и статус

Требование Rudra (basis: quoted): «как только возникают проблемы/сбои/дефекты —
автоматически на багфикс, письмом в сессию мастерской по канону»; enforcement
должен быть программным, «не только текст в AGENTS»; дизайн-требующая работа
остаётся `proposed` до approval Rudra.

Эта спека — proposal, не разрешение на runtime-код. Реализация начинается
только после reviewer → verifier PASS и отдельного approval Rudra. Не
ослабляет approval gates, запреты секретов или project ownership.

## 2. Цель

На инфраструктурном сбое система обязана создать видимый metadata-only incident,
поставить обязательный workflow gate для агента-primary и оставить проверяемый
статус: письмо должно быть отправлено в активную bugfix-сессию либо явно
зафиксировано `route_state=blocked` с handoff. Listener (capture-плагин) не
отправляет письмо и не dispatch-ит агента; это делает primary workflow. Сбой
нельзя молча проглотить, считать исправленным только из-за workaround или
переводить в `general`.

## 3. События и цена

Первый детерминированный набор:

- permission gate: `permission.rejected`, включая `external_directory`;
- tool/channel: tool execution failure, timeout, failed subagent dispatch,
  schema/transport failure;
- plugin/script: исключение, ненулевой exit, ошибка загрузки;
- model/quota: model unavailable, quota/balance, upstream timeout.

Capture использует событие/код/имя инструмента и короткое очищенное описание;
без prompt, ответа модели, полного tool output, путей/значений, похожих на
секреты. Дедупликация по стабильному error-class + hint/session window. Capture
не должен ждать сеть/LLM, повторять неудачный вызов, блокировать штатный
инструмент или увеличивать стоимость выше самого сбоя. Повторяющиеся ошибки
агрегируются; неизвестный сбой виден как `unknown`, не отбрасывается.

## 4. Incident record

Каноническая форма реестра:

`symptom → repro → root cause → fix/workaround → evidence → status`

Минимальные поля: incident/task ID, timestamp, error class, source/tool,
короткий redacted symptom, repro hint, root-cause hypothesis vs confirmed,
fix-route, evidence reference. Incident `status` наследуется из рабочей
(draft) `bugfix-proactive-plugin.md` S4: `open|reported|dispatch|fixed|rejected|deferred|deferred-after-B9`.
Отдельное поле `route_state: ready|blocked|unknown` показывает отсутствие
адресата/канала и не подменяет incident status. S4-enum обязателен для
машиночитаемых BF-записей; свободная форма статуса в повествовательном
реестре мастерской — не machine contract. Статусы самой задачи (`proposed`,
затем по решению Rudra) не являются incident status. Источник истины для
записи — проектный incident registry/handoff; runtime state — только metadata.

## 5. Каноническая маршрутизация

1. Обязанность по письму — у агента-primary в обязательном workflow gate; capture
   listener только создаёт metadata event/сигнал по канону draft-спеки плагина
   (substance approved, S2) и сам ничего не отправляет.
2. Когда адресат доступен, primary workflow отправляет письмо только через
   `tools/peer-comms/letter.sh`, соблюдая B18: один `message_id`, `started` при
   получении, `finished` с artifact/SHA или один конкретный `cannot`;
   duplicate-send запрещён.
3. Получателя искать через `hello.sh find --role bugfix` (или утверждённый
   Rudra эквивалент); session ID нельзя угадывать или хардкодить без срока.
4. Сейчас claims registry не показывает активную роль `bugfix`. До регистрации
   canonical bugfix-сессии автоматический адресат не определён. При отсутствии
   адресата listener даёт видимый сигнал, а workflow gate primary закрывает ход
   с `BLOCKED: no active bugfix session` и append-only handoff/incident; silent
   fallback запрещён.
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

1. Fixtures для каждого класса из §3; каждое событие даёт ровно одну безопасную
   запись либо дедуп-count, без prompt/output/secrets.
2. `external_directory` отказ и ошибочный skill/tool schema приводят к видимому
   incident и маршруту; `[проверить]` — реальное событие в OpenCode V2.
3. При отсутствии active `bugfix` claim выводится BLOCKED, а не ложное `sent`;
   при наличии тестового active claim письмо отправляется только через
   `letter.sh`, receipts соответствуют B18.
4. Healthy tool call — no incident; инструмент не блокируется и не повторяется.
5. Zero-LLM capture, redaction, dedup, latency/overhead и restart/disable
   проверены реальным verifier-прогоном.
6. Reviewer возвращает findings; только verifier выносит PASS/FAIL.
7. Rollback — выключить listener/feature flag; штатные вызовы продолжаются;
   записанные metadata incidents не удалять.

## 9. Вне scope и blockers

- Изменение Vault `opencode.json` не входит в dotfiles edit scope. INC-5
  передаётся Vault owner отдельным handoff; до его применения external-directory
  инцидент остаётся blocked/unverified.
- Источник — вложение `bugfix-extdir-and-rule-20261010.txt`; полный текст не
  копируется в runtime logs. Точные требования процитированы в §1.
- OpenCode core/tool API не патчить; runtime недоступность описывать как
  `[проверить]` с workaround.
- `system-ops` сохраняет существующую узкую external-directory область
  canonical bridge; этот high-risk boundary не расширять данным proposal.
- Не устанавливать/удалять пакеты, не менять `/etc`/сервисы, не включать
  `push --force`.
