---
description: Первичный разбор сбоя → incident record → named fix-route. Не подменяет approval и verifier.
agent: sysop
subtask: true
---

# Пайплайн: Разбор сбоя (BF-20261010-01)

Сбой: $ARGUMENTS

## Шаг 1: Capture-сигнал

Проверить capture-лог `~/.local/state/opencode/incidents/<project>.djsonl`
(агрегат — `incidents-index.jsonl`): есть ли уже запись по этому классу
(`count>1` — повтор). Сигнал плагина — обнаружение, НЕ инцидент и не статус.

## Шаг 2: Incident record

Создать/дополнить запись по форме `docs/incident-record-template.md`
(symptom → repro → root cause → fix/workaround → evidence → status).
Поле status — enum `open|reported|dispatch|fixed|rejected|deferred`;
переходы — только закрытый список спеки (§4). Гипотезы помечать явно,
факты — с evidence. Секретов, prompt'ов и absolute paths в записи нет.

## Шаг 3: Маршрут

Взять `recommended_route` из сигнала (S6), подтвердить или заменить
осознанно (авто-dispatch запрещён). Адресат письма, если нужен живой ответ:
`tools/peer-comms/hello.sh find --role bugfix`; активной роли нет →
`route_state=blocked`, append-only handoff, silent fallback запрещён.
Письмо — только `letter.sh` с двойным ack (B18), deadline квитанции 600 с.

## Шаг 4: Фикс и приёмка

Дорогой/дизайн-требующий фикс — задача с ID, `proposed` до отдельного
approval. Точечный — именованный исполнитель зоны, фикс в `task/*`-ветку,
приёмка — verifier (PASS/FAIL только verifier). После PASS — статус `fixed`,
оценка «не баг, а фича» (одна строка, false — норма).
