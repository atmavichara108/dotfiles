---
type: Research
title: И-35-A + И-38-A — инвентарь telegram и Vault-стейт (Волна 3, шаг A)
description: Два read-only исследования для решений Макса; предложения не канон.
timestamp: 2026-10-14
---

# И-35-A — телеграм-капчуры: карта инструментов и данных

## Два независимых инструмента (не один!)
1. **SSA-мост** (`scripts/.local/bin/tg-login/read/send.py`, ЗАКОММИЧЕНЫ `f592560` — предпосылка «untracked» была неверна): Telethon user-сессия, секреты `~/.config/ssa-tg/tg.env` (имена ключей: TG_API_ID/HASH/PROXY, SSA_GROUP_ID). `tg-read` пишет JSON `{id,date,from,text}` **на stdout** — персистентного файла капчура НЕТ (только маркер `last_id`, сейчас отсутствует → первый запуск перечитает всё).
2. **Vault vibeos-telegram-capture v0.1.0** (`~/Projects/OpenCode-Vault/tools/telegram-capture/`): полный конвейер (capture→classify→pipeline→mark→inbox_queue→watch), источник `@inbox_tools`, детерминированная классификация без LLM, тесты на месте. Данные: `captures_all.json` ~0.58MB + снапшоты, `signals.json` ~0.14MB.

## Для решений Макса
- **(2) сверка классификации:** реально только на vault-потоке (classified/signals есть). SSA-поток без классификации — моделировать с нуля.
- **(3) перенос в helpreg:** зависимости telethon(+socks/dotenv); конфиги вне репо (`tg.env`, `.env`, `*.session` — НЕ переносить в git); точка интеграции — hotmem/helpreg-записи с message_id/date.
- **(4) GLiClass:** поле `text` готово для классификации; объём ~0.5-0.66MB — локальный инференс реален; обучающая выборка — зависит от доли размеченного (пробел: счётчики не сняты — python/jq-гейт у субагента).
- **Риск дизайна:** SSA-капчур без файла на диске — исторические данные НЕ сохраняются (решение Макса: нужен ли persist).

# И-38-A — Vault-стейт машинных треков

- **control-plane TRACKED: 2579 файлов** (decision-queue 2571, telemetry 4, audit-log, model-catalog). Карточки РЕАЛЬНО коммитились в git.
- **Сейчас 5814 untracked грязных строк control-plane** (карточки сегодняшнего дня + evt_*), дерево Vault грязнится ежесекундно.
- **Гейт-факт:** `git -C ~/Projects/OpenCode-Vault` из workdir dotfiles — permission.rejected; работает только с `workdir=Vault`. Для дальнейшего аудита нужен workdir-режим или правка permission-паттерна.
- **Не дожато:** `.gitignore` Vault не прочитан, `git log control-plane/` (механика auto-commit) не снят, `decision-queue-hook.ts` кодом не подтверждён (гипотеза 195 битых JSON = конкурентная запись без atomic — ПОКА ПРЕДПОЛОЖЕНИЕ).
