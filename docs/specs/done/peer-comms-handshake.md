# Spec: Peer-comms handshake — рукопожатие параллельных сессий

---
spec: peer-comms-handshake
kind: task
status: done
spec-home: dotfiles/docs/specs/ (dotfiles repo)
owner: dotfiles primary (реализация в dotfiles-сессии)
mandate: Рудра, 2026-10-05 — «протокол рукопожатия... если нету нужно завести, это спек уже для дотфайла»
related: OpenCode-Vault [[02-Methods/peer-comms]], [[02-Methods/parallel-sessions]] §L2, tools/peers/peer_role.py
verifier: required (dotfiles-. worktree fork)
---

## S1. Проблема

Параллельные сессии OpenCode (первый живой обмен — librarian ↔ idea-graph v2,
2026-10-05) общаются письмами по peer-comms, но без программного рукопожатия:
нельзя детерминированно узнать, кто рядом, жив ли сосед, на какой модели
и с каким scope. Существующий L2-чекоут — метод уровня согласования,
не runtime-протокол; peer_role.py — сигнализация, не рукопожатие.

Повторённый живой факт (инцидент 2026-10-05): `opencode run -s <id> -m ...`
блокирует ход соседа > 120 с — таймаут письма должен быть ≥ 360 с, текст —
максимально короткий; модель всегда с флагом `-m` (модель отправителя).
Bootstrap-протокол у нас уже есть эмпирический: письмо → доставка →
квитанция → ack → append-узел в общий граф → коммит.

## S2. Требуется

1. **Скрипт/плагин** (размещение на усмотрение dotfiles primary; кандидат —
   расширение peer_role.py или новый плагин в `opencode-global/.../plugins/`):
   - `hello` — регистрация сессии: sessionID, роль/scope, модель, ts
   - `ping <sessionId>` — живость соседа (по claims + главное окно updated);
   - `bye` — release.
2. **Логика**:
   - hello/ping/bye — append-only строки в claims.jsonl (op: hello/ack/bye,
     поля session/model/scope/ts/TTL ≈ 30 мин); активные = без bye и свежие.
   - TTL старше 30 мин — сосед «спит» (писать ему не надо, но честно
     отобразить).
   - поддерживать минимум two-party handshake; больше параллельных — ок.
3. **Интеграция с общим полем** — опционально: hello/bye события
   поверх idea-graph (graph proto) — по усмотрению, не дублировать
   содержимо; или хранить всё в claims.jsonl, а в графе — лишь заметные
   события обмена (коммиты, квитанции).

## S3. Constraints

- hello/ping НЕ создают задач, НЕ дают прав (peering-сигнализация).
- Общий файл parsing — детерминированный, append-only, без LLM.
- Отражение модели/таймаутов: constants в скрипте, тестируются смоком.
- Не ломать peer_lease.py горячую линию. Все без `sudo`, работать от user.
- gitignore проверять на generated-файлы как у claims.jsonl.

## S4. Acceptance (смок)

Live-тест между двумя параллельными сессиями (актуальными):
1. `hello` в сессии A → сессия B видит через `ping` (TTL, модель, scope).
2. Письмо B → A: доставка подтверждена, ack коротким письмом, таймаут ≥ 360 с.
3. `bye` у A → перестаёт быть «активным» для B.
4. Кожевые смоки повторяются с worker TTL, истечение честно фиксирует.
5. Pre-commit/train, `verify.py --git` PASS в dotfiles.

## S5. Критерии качества

- скрипт FAIL-fast, без магических путей (константы сверху).
- вывод человеко-читаемый (таблица/JSON).
- не блокирует основной ход (TTL/memo кэш в ограничении).

## S6. Deliverables dotfiles

1. Скрипт/плагин + тесты (минимальный pytest или bash-смок).
2. Запись в `dotfiles/docs/decisions.md` (ADR-…). 3) Синхронизация
   `~/.config/opencode` (stow). 4) Update OpenCode-Vault peer-comms
метода дописью строки (текст — по факту реализации).

## Completion record (2026-10-06)

- Static verifier: PASS — syntax, shellcheck, JSONL append-only, malformed-line
  tolerance, TTL, ack/bye state, and `stow.sh verify_tools()`.
- Live two-party gate: PASS from librarian interactive session: librarian hello
  was visible to sysop via ping; ack record observed with `op: ack`; TTL/unknown
  covered by `tools/peer-comms/smoke.sh` (10/10).
- Canonical implementation: `tools/peer-comms/hello.sh` and `smoke.sh`.
- Runtime claims are ignored by git; no tasks, permissions, or secrets are
  carried by handshake records.
