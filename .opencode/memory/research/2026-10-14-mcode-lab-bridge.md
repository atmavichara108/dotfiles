---
type: Research
title: И-33 — лаба кода (мкод): состояние моста и портирование
description: Read-only итог по мкоду как доп. движку; предложения не канон.
timestamp: 2026-10-14
---

# И-33 — лаба кода (мкод), итог исследования

## Факт
- **мкод = M Code Desktop, форк OpenCode** (glossary.md:29): «дополнительный движок, заточен на разработку кода и интеграцию в систему, кроме системных глобальных конфигов opencode/mcode». Правило (glossary.md:30): opencode правим изнутри в границах; **мкод — только собирать баги и предлагать решения**, не модифицировать.
- Отсек «Кода (мкод)» (registry.md:35): лаба кода со своими контейнерами, мост и портирование; файловая зона пока `tbd`, нумерация не закреплена.

## Состояние моста mcode↔opencode
- **Сделано:** T-156 `mcode-opencode-bridge-endpoint.md` (verified-tech-pass) — направление M Code → OpenCode, обратно только git-tree handoff. Артефакты: `systemd user opencode-serve.service` (127.0.0.1:49374) + `scripts/.local/bin/opencode-bridge` (prompt/read/handoff). SSOT `mcode-opencode-provider-ssot.md` (done) — `mcode.jsonc` 8 провайдеров в dotfiles.
- **Не сделано:** ADR-019 — **ядро mcode глобальные плагины НЕ исполняет** (проверено 2026-10-01), agent/plugin-слои не паритетны. T-hooks (ротация пароля) частично.

## Барьеры портирования (вывод)
1. Плагины/агенты mcode не грузятся глобально → вся инфра (tree-hygiene, branch-auto) в mcode не работает, только git-pre-commit + AGENTS.
2. Конфиги дублируются (mcode.jsonc vs opencode.jsonc), SSOT — ручное удержание, дрейф не автоматизирован.
3. Ключи разнесены (secret-service vs auth.json/.env) — причина падений провайдеров.
4. Бан на правку движка мкода (только bug-collector).

## Предложения (не канон)
- **П-1:** закрепить зону отсека в локальном слое `dotfiles/.opencode/` + `docs/lab/mcode-notes.md`; глобальные `opencode-global/**` — red-line.
- **П-2:** bug-collector-режим — оформить барьеры как список багов/запросов разработчикам мкода (паритет hooks, глобальные плагины, sessionID для claim-гейтов).
- **П-3:** read-only регресс-чек лабы через `opencode-bridge read/handoff` + сверка SSOT-провайдеров.

## Пробелы
`systemctl is-active opencode-serve` сейчас недоступен researcher (permission); подтверждение live — 2026-10-06. Версия mcode-bin и хвост ADR не дочитаны.
