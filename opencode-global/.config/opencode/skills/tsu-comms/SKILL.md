---
name: tsu-comms
description: Сверхнавык ЦУ №2 «Коммуникация/отладка» — мандат ведомству, калибровка адресов, диагностика канала peer-comms. Использовать при «поставь задачу ведомству», «напиши ИЦ», «канал не работает», «почини доставку». Пользовательский вход — /dispatch.
metadata:
  opencode/slash: "true"
---
# tsu-comms — сверхнавык «Коммуникация/отладка» (Р-003 навык 2)

## Постановка (мандат ведомству)
1. Адрес — только полный sessionID из 04-Memory/peer-registry.md (класс INC-18: адрес из чата запрещён); нет адреса/ведомства → UNROUTABLE, не угадывать.
2. Route decision по [[02-Methods/capability-routing]]: capability, scope, risk, mutability, review, acceptance, fallback.
3. Постановка: дословное слово владельца (basis: quoted) либо явная пометка «по распоряжению ЦУ»; scope; DoD; что не трогать; ref-id.
4. Отправка: /home/rudra/dotfiles/tools/peer-comms/letter.sh --to <id из реестра> --from <свой id> --scope <ref> --title … --file …; модель адресата НЕ передавать (B15); garbage-guard перед отправкой. Если letter.sh застревает на drain старой очереди — прямая отправка `opencode run -s <id> -- "<payload>"` (rc=0 критерий), письменно отмечая в session-log.
5. Delivery-check: sent ≠ delivered — сверяй журнал receipts-out.jsonl (event=sent/timeout/queued).

## Отладка канала
Симптомы→действия: письма дублируются → проверь pending.jsonl (attempts, повторный инжект) и жди патч queued-журналирования; письма не доходят → grep receipts-out по from/to, проверь event; канал падает синтаксически → проверь маркеры слияния `grep '<<<<<<<'` в tools/peer-comms/letter.sh, восстановление `git checkout HEAD -- tools/peer-comms/letter.sh` (чужие stash не трогать). Инцидент по [[02-Methods/incident-fix]]: симптом → repro → гипотеза → named fix-исполнитель (Мастерская) → evidence.
