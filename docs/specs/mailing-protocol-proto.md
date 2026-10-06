---
kind: spec
status: proto-draft (элементы design; до мандата не реализуется)
title: Программный протокол писем (двойной ack + read-gate + JSONL receipts)
spec-home: dotfiles (рядом с peer-comms-handshake)
date: 2026-10-06
author: igraphv2
owner-slot: dotfiles/sysop (коммит делает sysop после приёмки)
basis: 02-Methods/peer-comms (канал), 02-Methods/team-protocol (§5), handoff
       2026-10-06-bugfix-logging-research (дополнительное поручение), blessing Рудры
       «подтверждаю всё», направление Дирижёра (double-ack/deadline/idempotency)
---

# Программный протокол писем (proto)

## Цель

Письма между сессиями проходят через программный контур: read-gate, двойной
ack (started/finished), JSONL-квитанции у обеих сторон, deadline без ложных
«провалов», идемпотентность (запрет дублей). Всё детерминированно, без LLM
в цикле (фильтр устойчивого развития).

## Поверхность

Рядом со спекой `peer-comms-handshake.md` (приём «hello»); это — исполнительная
поверхность протокола писем, не замен. Хост: `~/.local/state/opencode/mail/`
либо `control-plane/mail/` (уточнено при реализации sysop; state-path по правилу проекта).

## Модель события

| Код | Кто пишет | Что значит | Файл |
|---|---|---|---|
| `sent` | отправитель | письмо отправлено (message_id, digest, ts) | receipts-out.jsonl |
| `read` / started | получатель | приступил (первый ack; read-gate) | receipts-in.jsonl |
| `finished` | получатель | завершил (артефакт/SHA) | receipts-in.jsonl |
| `cannot` | получатель | «не могу» с одним блокером | receipts-in.jsonl |
| `unknown` | отправитель | deadline истёк без ack — не «провал» | receipts-out.jsonl |

Правила:
1. `message_id` — детерминированный (hash тела + номер дня + session_id).
2. Повторная отправка того же `message_id` запрещена (no-resend); OUT-скрипт
   сверяет `digest` по записи и молча отклоняет дубль.
3. read-гейт: приёмник отвечает `started` при первом контакте — даже без
   начатой работы; это и есть «сообщение прочитано» destructive-free.
4. deadline semantics: после deadline — `unknown`, не failed; получатель
   свободен; координатора уведомит отдельно; продление — новое письмо
   (новый message_id).
5. receipts обеих сторон append-only; ack-запись у приёмника ведётся в
   receipts-in.jsonl (не дублиcanonical OUT-канал).
6. Никаких secrets/полного тела письма в receipts — только
   metadata (id/digest/ts/scope/source session).
7. Совместимость с peer-comms канону: «письмо — короткое; reply через
   файл» — read через `opencode read` / session API; delivery gate —
   только программно.

## Что дополнить (вопросы к владелцу handshake-спеки/sysop)

1. ГДЕ живёт canonical receipts: `~/.local/state/opencode/` — state; или
   `control-plane/mail/` — per-репо, но не для cross-project? (сейчас: рекомендую
   state-папку для receipts + Control-Plane сводка отдельно).
2. Нужен ли TTL/sessionId по координатору в «route-log»: сверить механизм
   past-note «файл route-log/handoff» как запасной канал при сбоях.
3. Размер digest: hash-SHA (предпочтительно SHA-256 с короткой подписью
   «кто/когда») — реализуемо без LLM.
4. Формат связки с `team-protocol` §5: указать exact path/условие запасного
   канала при недоступности.

## Acceptance (после мандата реализации)

- smoke: (1) отправка двух писем «same id» → второй молча отклонён; (2)
  read-gate started живьём (session API проверка); (3) deadline → unknown,
  не failed; (4) receipts обеих сторон append-only; (5) zero-LLM: никакой
  классификации текста в цикле.
- reviewer + verifier, потом коммит sysop.
