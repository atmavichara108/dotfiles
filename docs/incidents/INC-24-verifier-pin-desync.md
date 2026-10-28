---
type: Incident
title: "Пин verifier рассинхронизирован между копиями (двойной префикс + недостижимый провайдер)"
status: resolved (re-pin по слову владельца: 4cb130e — verifier→muse-glimmer-30b, obsidian-servant→amd-radeon/GLM-5.3-Flash; nemotron ненадёжен)
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
