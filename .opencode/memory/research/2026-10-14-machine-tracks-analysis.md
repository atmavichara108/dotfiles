---
type: Research
title: И-38 — машинные треки: анализ и сдвиг scope
description: Read-only анализ decision-queue карточек; ключевой вывод — чистить надо в Vault, не в dotfiles.
timestamp: 2026-10-14
---

# И-38 — чистота дерева: машинные треки (анализ)

## Ключевой вывод (сдвиг scope)
Тела, «грязнящие дерево», лежат в **`OpenCode-Vault/control-plane/`**, НЕ в dotfiles. Значит `.gitignore`-чистка — это **Vault-репо**, отдельный scope (не dotfiles). В dotfiles этих файлов нет.

## Счётчики (read-only)
- **Vault** `control-plane/decision-queue/cards/`: **7706** json, парсятся 7538, **битых 195** (обрезаны в EOF — race при concurrent-write, не битые данные). `recommendation.class`: **nomenclatural 7296 · substantive 242** (≈96.8% шум).
- **Локально** `~/.local/share/opencode/decision-queue/cards/`: **8277** json, битых 0, но `recommendation.class` **отсутствует у всех** (NO_CLASS 100%) — схема не совпадает с vault. Risk: low 6207 · high 3394 · critical 396 · medium 320.
- **model-catalog.json** (69KB) и **audit-log.jsonl** (36KB) — тоже в `Vault/control-plane/`, generated-кэш/журнал.
- Размеры: vault control-plane ≈33M, локальный ≈36M. Счётчик vault растёт на глазах (каждое permission-событие = карточка).

## Гипотеза подтверждена
«Карточка на каждое permission-событие, поток зашумлён авто-апрувами» — ДА: 96.8% nomenclatural, substantive лишь 242 («ценных дилемм единицы»). Каталог рос на ~24 карточки за минуты анализа.

## Proposed-решение (СХЕМА, НЕ применено — Vault-репо, отдельный approval)
1. **Битые JSON (195):** не чинить, а чинить **писателя** (`decision-queue-hook.ts` — atomic rename/temp-file вместо конкурентной записи). Хвосты битых — удалить (metadata-only).
2. **`.gitignore` в `OpenCode-Vault/.gitignore`** (не dotfiles!): `control-plane/decision-queue/cards/`, `control-plane/model-catalog.json`, `control-plane/audit-log.jsonl` (+ `.meta-worktrees/*/control-plane/**`, `OpenCode-Vault-tasks/*/control-plane/**`).
3. **Сохранить:** 242 substantive-карточки vault, 4 seeded-карточки 2026-09-05, `SCHEMA.md`. Остальное (~7296 nomenclatural + 8277 local NO_CLASS) — шум.
4. `audit-log.jsonl` — append-only журнал; если как evidence — не gitignore, а периодическая ротация.

## Пробелы (не дожато)
Git-трекинг `control-plane/*` в vault (`git ls-files`), содержимое обоих `.gitignore`, trigger-условия `decision-queue-hook.ts` (эмпирика подтверждена, кодом — нет), локальная схема без `recommendation.class` — расхождение.

## Следствие для dotfiles
И-38 в dotfiles-очереди по сути = зафиксировать этот сдвиг и передать чистку в Vault-сами .gitignore-правки в dotfiles не нужны.
