---
type: Spec
kind: task
title: "Спека: Lineage-реализация (И-53, шаг 2)"
project: dotfiles
task: i53-lineage-20261016
status: ready — к исполнению (ревью архитектуры провёл ИПТ над ADR; спека операционализирует approved-дизайн)
timestamp: 2026-10-17
---

# Спека: Lineage-реализация (И-53, шаг 2)
- **Canonical design:** ADR-028 v2 (docs/decisions.md, коммит 9db6e34) — спека НЕ дублирует архитектуру, только операционализирует.
- **Владелец спеки:** ЦУ. **Реализация:** dotfiles-infra (ИЦ). **Гейт:** verifier PASS → приёмка Rudra.
- **Статус:** ready — к исполнению (ревью архитектуры провёл ИПТ над ADR; спека операционализирует approved-дизайн).

## Работы (R1–R7)
**R1. Ledger-инфра.** Файл ~/.local/state/opencode/lineage/ledger.jsonl (создать, права 600). Все записи под flock (одна на весь append; записи длиннее pipe buffer). Два API записи: add_event (append-факт: рождение, delivered-to, ack) и revise_status (новая запись-ревизия с тем же session_id и полем rev; состояние = последняя ревизия; in-place правки запрещены).
**R2. Birth-time записи.** (а) Автоклейм И-51 (branch/worktree creation) расширяется до полной lineage-записи: session_id, parent, born{via,ts}, branch, worktree, task, status: live; dual-write: git config branch.*.owner остаётся для per-repo читаемости, истина — ledger. (б) letter.sh: при отправке append ребра delivered-to (message_id, from, to, ref, ts) под flock. (в) Ребро forked-from — НЕ пишет letter.sh: импортируется из opencode.db (ядро; таблица session_v2, поля parent_id/fork_session_id/fork_boundary; типы рёбер: forked-from / child-of / letter-spawned — по механизму рождения; сироты parent_id IS NULL → запись orphan: true, никогда не отбрасываются; 255 известных — первый список аудита).
**R3. lineage-audit (tools/lineage/audit.py).** Только читатель opencode.db (никаких записей в чужие таблицы). Источники: session_v2, git refs + worktree list, receipts (~/.local/state/opencode/mail/), ledger. Правила отчёта: orphan-ветки (нет владельца/сессии); stale (≥10 коммитов позади origin/main на момент аудита ИЛИ ≥3 дней от последней lineage-записи ветки); письма delivered-без-processed старше 48ч; безродные неперсональные сессии; divergence открытых PR. Выход: отчёт + список тикетов (не молчание). Ротируемый снапшот ledger рядом (lineage/ledger.snapshot.jsonl, keep 5).
**R4. Миграция claims.** Обе копии claims.jsonl (dotfiles tools/peer-comms/claims.jsonl + волт tools/peers/generated/claims.jsonl) — одноразовый скрипт миграции в ledger; содержимое сохраняется целиком; оригиналы помечаются legacy-заголовком «мигрировано в ledger, дата, коммит», НЕ удаляются.
**R5. Ack (доставка ≠ обработка).** Стадия sent→delivered→processed. processed фиксируется: ответом адресата с тем же ref (letter.sh при отправке ответа пишет ack-событие) или явной командой ack <ref>. Аудит показывает только необработанные старше 48ч — без бюрократизации каждого письма.
**R6. Интеграция /ship.** Перед ship ветки: (1) stale-gate из R3 — ветка ≥10 позади или ≥3 дней без синка → обязательный merge origin/main в ветку; (2) conflict-preview перед PR: git merge-tree origin/main...HEAD, список конфликтных файлов до открытия PR.
**R7. tg-bridge parent — отдельная задача.** Зонд: один мост, kill-criterion «мост после фикс записывает parent у ≥1 новой сессии; поломка логики моста → откат»; после PASS — тираж. НЕ следствие ledger.

## Acceptance (DoD = ADR-028)
0 orphan-веток в отчёте; 0 новых безродных сессий от писем/tg; каждая отправка видит стадию processed; stale-ветки видны ДО открытия PR; живой аудит выдаёт чистый отчёт или тикеты. Все гейты pre-commit + verifier PASS.

## Границы
Пять реестров не удаляются (кроме миграции claims); никаких временных/промежуточных механизмов; код приложений не трогается; opencode.db — read-only; ничего не ломать в работающем (защищённый конец штанги, метод fail-fast волта, main 576d636).

Связано: ADR-028 v2, И-53, И-51, peer-review ИПТ 2026-10-16/17.
