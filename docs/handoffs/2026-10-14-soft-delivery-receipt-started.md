# Incident record — INC-14: мягкий сбой доставки peer-comms (receipt-started без sent)

> Форма канонична (BF-20261010-01 §4). Гипотеза ≠ факт: неподтверждённое
> помечаю `[гипотеза]`. Секретов, prompt'ов, model output, absolute paths и
> сырого stderr в полях нет.

- **Incident ID:** INC-14
- **ts:** 1791941906
- **error class:** tool-fail
- **source/tool:** peer-comms/letter.sh
- **route_state:** ready (заявка от Центрального Узла, тикет ses_ecae229fcffef5FrLdWOJLos1K)
- **notification_state:** started (квитанция letter.sh от 2026-10-14, ref 76d16d6e…)

## Symptom
Письмо-квитанция `receipt-started` зафиксировано в `receipts-out.jsonl`, но без
события `sent`; в сессии-получателе письмо не появилось. Отправитель посчитал
доставку успешной, хотя она не завершилась.

## Repro
`letter.sh --receipt started --ref X --file F` с таймаутом у вызывающей сессии
(например 180 с). Журнал пишет `receipt-started` до блокирующего `opencode run`;
если процесс убит таймаутом на середине инъекции — `run-rc` не успевает
записаться, exit-код не отражает недоставку.

## Root cause
`[подтверждено чтением кода]` В `letter.sh` журнал (стр. 160–169) пишет событие
`receipt-${receipt}` / `sent` **до** блокирующего вызова `opencode run` (стр. 172),
осознанно — чтобы факт отправки не терялся при убийстве процессом (комментарий
стр. 158–159, инцидент B18). Следствие: для receipt-режима событие становится
оптимистичной фиксацией «отправлено»; фактическая доставка не верифицируется
(`delivery-check` для receipt-режима не вызывается), и `run-rc` при мягком
таймаут-убийстве не пишется — журнал застревает на `receipt-started`.

## Fix / workaround
- **Workaround (принят ЦУ, действующий):** после `letter.sh --receipt …` проверять
  наличие события `sent`/`finished` в `receipts-out.jsonl` (или `delivery-check.sh`
  по ref); при отсутствии — считать доставку несостоявшейся.
- **Fix (предложение):** в `letter.sh` для receipt-режима после `opencode run`
  вызывать верификацию доставки (delivery-check по ref); событие `sent`/`finished`
  писать только post-verified, иначе — nonzero exit + событие `undelivered`.
  Сохранить «факт не потерян»: вести отдельное поле `attempted` до вызова и
  `delivered` после проверки, не смешивая оптимистичную и подтверждённую фиксации.
- Чужой харнесс не патчим; это dotfiles-инфраструктура — в нашей компетенции.

## Evidence
repo=dotfiles sha=<в коммите> path=docs/handoffs/2026-10-14-soft-delivery-receipt-started.md
+ journal receipts-out.jsonl: `receipt-started` f18cb77f… без последующего `sent`;
  letter.sh стр. 157–177 (журнал до вызова, run-rc только на явном rc!=0).

## Status
`open` → запись заведена; воспроизведение и точечный фикс letter.sh — на
рассмотрение (предложение выше). Закрытие — после фикса и live-проверки.