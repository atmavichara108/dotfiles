# Incident record — письма в сессию ДВ-Хаб «sent», но не доходят (dvhub-inbound)

- **Incident ID:** INC-21
- **ts:** 1792837162 (2026-10-24 13:19); доклад Мастерской 2026-10-25, ответ 2026-10-26
- **error class:** channel-loss / false-sent (seen-before: INC-18)
- **source/tool:** `tools/peer-comms/letter.sh` (`_run`, `_inject`, `drain_queue`)
- **route_state:** fix-in-tree (`f00add4`, ветка `task/fix-peer-mail-20261024`); push — ждёт `/ship`
- **notification_state:** ответ Смотрителю ДВ-Хаб доставлен ship-mail 2026-10-26

## Symptom
Письма, адресованные `ses_ea5bee799ffes5WDriyP61xyB5` (Смотритель ДВ-Хаб),
не доходили; в журнале при этом `event=sent` — отправитель считал их
доставленными. После провального прогона письмо исчезало из очереди.
2 из 2 воспроизведения стабильны.

## Repro (дословно от адресата)
1. `letter.sh --to ses_ea5bee799ffes5WDriyP61xyB5 …` → journal `sent`;
   затем `event=run-rc rc=1 stage=drain` (мгновенно).
2. `grep ses_ea5bee… pending.jsonl` → записей нет (payload уехал в `done/`).

## Root cause (из кода канала, не догадка)
1. **Журнал писал успех ДО прогона:** `_inject` ставил `sent` до `opencode run`;
   при провале запись оставалась «доставленной».
2. **`if` без `else` глотал код возврата:** у `if cmd; then …; fi` при провале
   условия статус блока — всегда 0; rc доставки превращался в 0 («delivered»).
3. **stderr удалялся сразу** (`rm -f "${errf}"`), а в ветке без агента шёл в
   `/dev/null` — причину падения поймать было нечем (отсюда INC-18-формулировка
   «причина не установлена»).
4. После провала `drain_queue` безусловно переносил payload в `done/` — письмо
   терялось без следа.

## Fix
- Журнал «итог» пишется ПОСЛЕ прогона: `delivered` при rc=0, `failed` при rc≠0
  (добавлено ранее в дереве).
- stderr провала больше не стирается: хвост 600 б в журнал (`stderr_tail`),
  полный файл — `<mail>/errors/<mid>.txt` (`f00add4`).
- Проверено живым прогоном: провал → `{"event":"failed","rc":124,"stage":"drain"}`,
  успех → `{"event":"delivered"}`.

## Evidence
- Журнал: `~/.local/state/opencode/mail/receipts-out.jsonl` — записи `failed`
  с rc и stage.
- Тест-прогон: `PEER_COMMS_RESERVE=1 PEER_MAIL_DIR=/tmp/opencode/mt3 … letter.sh --to
  ses_eceb23… → RECEIPT + event=sent`.
- Ответ Смотрителю: ship-mail `20261026T000059_efbd336a10db` (ref `dvhub-inbound-20261024`).

## Гипотезы адресата — сняты
- H1 (модель `nvidia/z-ai/glm-5.3#thinking` не резолвится) — опровергнута:
  прогоны стартуют (`> build · z-ai/glm-5.3`), упираются только в мой таймаут.
- H3 (cross-project) — снята тем же контролем.

## seen-before
INC-18 (`address-error / false-positive-delivery`): тот же корень «журнал
сообщает успех, которого нет». Дисциплина seen-before выполнена: referencia
дана; диагностика с нуля не повторялась по классу доставки.

## Открытые хвосты
- Push `f00add4` — ждёт `/ship` (иначе правка мёртвая для остальных сессий).
- Канон Р-028: `letter.sh` — резерв (deprecated); рабочая почта — `ship-mail.sh`.
  Это и есть системное лечение класса channel-loss: файловая шина без модели.
