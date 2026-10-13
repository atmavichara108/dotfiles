---
type: Spec
title: orch-guard v1 — учёт оркестрации кодом, а не памятью
description: Ledger диспетчерских вызовов + гейт перед dispatch + теневой плагин-дописчик; правила orchestration.md, исполняемые программно.
timestamp: 2026-10-14
status: approved
spec-home: docs/specs/
owner: bash-dev + meta → verifier
---

# orch-guard v1

Заказ Макса (2026-10-14, basis: quoted): «выписать всё важное и сделать чтобы
работало программно, без забываний» — по `.opencode/memory/orchestration.md`.

## Что исполняется кодом

| Правило | Где |
|---|---|
| Не более 3 активных задач в пересекающихся зонах (researcher/verifier — всегда можно) | `orch-guard.py dispatch` — отказ rc=2 |
| Повтор ≤2 без `--force-wave --reason`; повтор с запретом прошлого сбоя | `dispatch --retry`, текст запрета — в скопе вызова |
| Пин `model:` на free-моделях запрещён (роняет вызов в `tool_choice`) | `dispatch --model *free*` при free-primary — отказ rc=2 |
| Вердикт — только `--by verifier` | `verdict` — отказ иначе |
| Ledger ведётся даже если primary забыл CLI | теневой плагин `orch-guard.ts` (только append, effect не меняет) |
| Секреты не попадают в ledger | эвристика-отказ rc=3 |

## Что остаётся текстом (не кодируется)

Вход/границы/deliverable в каждом вызове; «отчёт проверять, а не принимать»;
дробить долгие исследования; протокол переезда между моделями; завершение
волны (чек-лист, не гейт).

## Границы

Данные — вне репозитория (`~/.local/state/opencode/orch-guard/`).
Плагин теневой: никогда не меняет effect и не блокирует.
