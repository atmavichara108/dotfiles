---
type: Incident
title: "tg-guard: журнал молчал при живом процессе — два корня (прокси-реконнект + копия сессии)"
status: resolved-fix (шаг владельца: отдельный логин сторожа)
timestamp: 2026-10-28
ref: tg-guard-journal-silent-20261028 (control-top → ИЦ)
---

# INC-23: молчащий журнал сторожа TG

## Symptom
tg-guard.service жив, telethon-сессия обновляется, но guard-journal.jsonl
молчал с 2026-10-22 (последняя запись id 181). Новые сообщения топика 33
(id 183 медиа, 184/185 тестовые) в журнал не попадали.

## Repro
- journalctl --user -u tg-guard.service: цикл 'Server closed the
  connection' каждые ~2с при живом процессе (до фикса);
- pgrep: процесс жив; ssa-guard.session обновляется;
- сообщение из основной сессии (tg-send, id 184/185) → событие у сторожа
  НЕ наступает.

## Root cause (два, layered)
1. Прокси-реконнект: Happ-прокси переключал режимы (tor), клиент висел в
   reconnect-loop без backoff, без visibility. → сердцебиение + outage +
   exit(75) с само-перезапуском (свежий env).
2. КОПИЯ СЕССИИ: сторож работает на копии ssa.session (ssa-guard.session) —
   это тот же auth-key. При живом основном клиенте сервер маршрутизирует
   события в основную сессию; копия подключена, но события не получает.
   Молчание без единой ошибки — ровно класс «тишина ≠ здоровье».

## Fix
- Heartbeat (30с) + outage-запись (guard-outage.jsonl) + exit(75) после 4
  обрывов — в tg-guard.py и dv-tg-guard.py (реальные демоны); архивная
  копия — в tg-watch.py для ручных прогонов.
- tg-attach.py: явные таймауты на download (TG_ATTACH_TIMEOUT, default 60с)
  вместо молчаливого hang в tor-режиме (control-top: 120с без вывода).
- tg-login.py: --session-name — вход ОТДЕЛЬНОЙ сессии сторожа (своя auth,
  свой поток событий). Шаг владельца:
  python3 ~/dotfiles/scripts/.local/bin/tg-login.py --session-name ssa-guard.session
  (код из Telegram вводит владелец), затем рестарт сторожа.

## Evidence
- heartbeat: 'tg-guard: alive topic=33 connected=True' (23:00, 23:05).
- send 184/185 → ok, у сторожа события нет (копия-сессия, доказано).
- SSA-guard.session mtime = время подключения, процесс active.

## Следствие
Пока сторож на копии — журнал будет пустым при живой основной сессии.
После отдельного логина потоки разделятся, журнал оживёт. Старые записи
(append-only) не переписываются; пропуск 182-183 — следы outage-окна.
