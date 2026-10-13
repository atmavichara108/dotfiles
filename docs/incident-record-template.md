# Incident record — <короткая метка>

> Форма канонична (BF-20261010-01 §4): symptom → repro → root cause →
> fix/workaround → evidence → status. Гипотеза ≠ факт: неподтверждённое
> помечать `[гипотеза]`, непроверенное — `[проверить]`. Секретов, prompt'ов,
> model output, absolute paths и сырого stderr в полях нет — только очищенная
> метка и непрозрачный evidence-ref.

- **Incident ID:** <INC-N / BF-YYYYMMDD-NN>
- **ts:** <epoch>
- **error class:** <tool-fail | provider-unavailable | provider-quota | provider-timeout | permission-blocked | unknown>
- **source/tool:** <tool | provider | permission>/<имя инструмента без путей>
- **route_state:** <ready | blocked | unknown>
- **notification_state:** <not_required | pending | sent | started | finished | cannot | unknown>
  - B18: письмо только `letter.sh`; rc `delivery-check.sh` 0/1/2 — коды процесса,
    не notification state; `unknown` — только после deadline 600 с без `started`;
    повтор того же `message_id` запрещён.

## Symptom
<что наблюдали, одной строкой>

## Repro
<минимальный воспроизводимый шаг, без секретов и путей>

## Root cause
<подтверждённая причина; если hypothesis — так и подписать>

## Fix / workaround
<что сделали; чужой харнесс не патчим — workaround + запись-факт>

## Evidence
<repo=<slug> sha=<40hex> path=<repo-relative> или opaque ID; после secret scan>

## Status
`open → reported → dispatch → fixed` — закрытый список переходов §4;
`open|reported → rejected|deferred`; `dispatch → open` (откат маршрута);
`fixed → open` (reopen с новым symptom). Иное — запрещено.

## Не баг, а фича (опционально, после verifier PASS)
- has-feature-potential: <true|false>
- feature-evidence: <одна строка, ≤150 символов; false — нормальный ответ>
