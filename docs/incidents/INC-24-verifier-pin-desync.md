---
type: Incident
title: "Пин verifier рассинхронизирован между копиями (двойной префикс + недостижимый провайдер)"
status: resolved-fix (слово владельца 2026-10-29, вариант (а), via ЦУ)

## Переоткрытие (проверка ЦУ по диску, 2026-10-29)
- Проектная копия .opencode/agent/verifier.md = nvidia/meta/muse-glimmer-30b
  (4cb130e, рука владельца) — ИСПРАВНА; пин валиден: каталог моделей
  содержит nvidia/meta/muse-glimmer-30b, провайдер nvidia живой.
- Глобальная копия opencode-global/.config/opencode/agent/verifier.md В MAIN
  по-прежнему nvidia/nvidia/nemotron-... (двойной префикс) — класс
  рассинхрона копий В ЖИВУЮ. resolved при живой битой копии = фикция.
## Исполнение (2026-10-29, слово владельца вариант (а))
- Глобальная копия приведена к единому пину: model: nvidia/meta/
  muse-glimmer-30b — байт-в-байт совпадает со строкой проектной копии.
- Валидность: каталог моделей содержит nvidia/meta/muse-glimmer-30b под
  провайдером nvidia (он же живой — на нём ходит сессия ИЦ).
- Evidence (hashes после правки): проектная .opencode/agent/verifier.md =
  4247eb3e7d1f5fcd…; глобальная opencode-global/.config/opencode/
  agent/verifier.md = c6ccf42f7894019e…; model-строки идентичны.
timestamp: 2026-10-28
ref: verifier-pin-defect (ЦУ, исследование УАС)
---

# INC-24: пин verifier

## Symptom
Глобальная копия агента verifier несёт nvidia/nvidia/nemotron-3-nano-
omni-30b-a3b-reasoning — двойной префикс провайдера + провайдер nvidia не
объявлен ни в одном конфиге и не в auth.json. Проектная копия —
muse-glimmer-30b. Полу-репин двух копий в разных состояниях хуже одного:
verifier может уехать по битой глобальной копии.

## Класс
«Пин рассинхрона копий» — агентские .md в двух слоях (глобал/проект)
разошлись; правило: изменения model: — шум, но РАСХОЖДЕНИЕ ломающее
достижимость — инцидент, не шум.

## Fix (только по слову владельца)
Re-pin verifier одной моделью в обеих копиях; объявление провайдера
nvidia (если владелец захочет) — зона ИЦ. Пока — жду слова.

## Evidence
Письмо ЦУ verifier-pin-defect (исследование УАС); system-update 10-28:
проектная копия переключена на muse-glimmer-30b.
