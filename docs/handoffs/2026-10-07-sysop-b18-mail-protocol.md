# Handoff — Sysop → Дирижёр: B18 программный протокол писем (double-ack), реализация

**Дата:** 2026-10-07
**Ветка:** task/mail-protocol-b18 (основа — main; старт был от 68f7663,
подхвачен актуальный main=c100e93 после мержа justwoker-шима Рудрой)
**Автор:** sysop (primary)
**Scope:** B18 — materialize спеки `docs/specs/mailing-protocol-proto.md`
(f748ee1, blessing Рудры). Прод-сессии и `.mcode` не трогались.

---

## Реализация (детерминированно, zero-LLM)

| Deliverable | Что делает |
|---|---|
| `tools/peer-comms/letter.sh` (изменён) | При доставке пишет `sent` в журнал `~/.local/state/opencode/mail/receipts-out.jsonl` (append-only, **metadata-only**: message_id/digest/to/from/scope/ref/rc/ts, без тела). `message_id` = sha256(тела)[:16]+YYYYMMDD+from. Повтор того же id — **DUP, отклонён** (no-resend). Новые флаги: `--from/--scope/--receipt started|finished|cannot/--ref` — обратно совместимы (B15-guard не тронут). |
| `tools/peer-comms/delivery-check.sh` (новый) | Read-gate: `delivery-check.sh <sessionID> <hash|substring>` по sqlite `session_message` (type=user, окно 7 дней, mode=ro). hash = префикс sha256 текста письма (учитывает обёртку кавычками, которой OpenCode ранит входящие). rc=0 доставлено / rc=1 нет / rc=2 ошибка. Зависимости: python3. `_ack-файлы /tmp/opencodeREAD` больше не источник. |
| `docs/specs/done/peer-comms-handshake.md` +S7 | Контракт поведения: получатель шлёт `started` при получении (read-gate «прочитано» без начатой работы), `finished` при завершении хода (артефакт/SHA); deadline → unknown, не failed. |
| `AGENTS.md` шапка «Протокол писем» | Живой контракт для всех агентов dotfiles (там же: канон letter.sh без `-m`). |
| `docs/specs/mailing-protocol-proto.md` | status: proto-draft → **materialized** (host-выбор зафиксирован: `~/.local/state/opencode/mail/`). |

## Приёмка (реальный прогон, sandbox-сессия `ses_eec924d1cffeQi0NV1D6TzngGF`, прод-переписка не тронута)

1. **Отправка → журнал**: письмо с digest `74145aba3ca924d2…` →
   `sent`-запись в журнале (message_id `74145aba3ca924d2-20261007-ses_eedd28…`) ✓
2. **delivery-check rc=0 (hash)**: `DELIVERED: match=hash:74145aba3ca924d2` ✓
   (найден ответ тестовой сессии: `msg_1179bcc89001fmTj5IOrXYHIHq seq=140`)
3. **delivery-check rc=1 (нет)**: `deadbeefdeadbeef` → `NOT-DELIVERED` ✓
4. **Идемпотентность**: повтор того же тела → `DUP … no-resend`, в журнал не
   записано, отправка не повторялась ✓
5. **receipt-письмо**: `--receipt started --ref 74145aba…` → событие
   `receipt-started` с ref в журнале; `delivery-check` по ref → rc=0 ✓
6. **B15-regression**: `--model foo/bar` на неизвестную сессию → **REFUSE rc=3** ✓
   (guard не сломан; journal-запись при REFUSE не пишется — exit до отправки)

Песочница журнала: `PEER_MAIL_DIR=/tmp/opencode/mail-b18-899273/` (env-переопределение
предусмотрено — прод-журнал `~/.local/state/opencode/mail/` в тестах не касался).

## Инцидент при работе (учтён)

Параллельная сессия (мерж justwoker-шима) переключила общий worktree на
`main → task/next-20261007-2110` посреди моей работы; мои три коммита легли
на её ветку. Разбор штатный: мой ref `task/mail-protocol-b18` переставлен на
`787b4ed` (contains my work, база — актуальный main c100e93); чужая ветка
`task/next-20261007-2110` оставлена нетронутой (её владелец решает, мержить
или rebase). Дрейд-факт: stow-симлинки + общий checkout = одна ветка на всех —
переключение чужой сессии перехватывает HEAD. Повторно: коммит-гейт стоит на
`task/*` — на чужой task-ветке он не сработал (не различает «чью» task-ветку);
отметку передаю Дирижёру как кандидат на доработку tree-hygiene.

## Repro

```bash
cd ~/dotfiles && git switch task/mail-protocol-b18
export PEER_MAIL_DIR=/tmp/opencode/mail-b18-repro-$(date +%s)
MSG="B18 repro $(date +%s)"
bash tools/peer-comms/letter.sh --to ses_eec924d1cffeQi0NV1D6TzngGF \
  --text "$MSG" --scope b18-repro          # доставит + sent-журнал
H=$(printf '%s' "$MSG" | sha256sum | cut -c1-16)
bash tools/peer-comms/delivery-check.sh ses_eec924d1cffeQi0NV1D6TzngGF "$H"  # rc=0
bash tools/peer-comms/delivery-check.sh ses_eec924d1cffeQi0NV1D6TzngGF deadbeefdeadbeef  # rc=1
```

## Артефакты

| Артефакт | SHA |
|---|---|
| код (letter.sh + delivery-check.sh) | `d1f2079` — letter.sh sha256 `70385b37ffdc56fe…`, delivery-check.sh `473e135a893de23b…` |
| спеки (S7 + materialized) | `0da960e` |
| AGENTS.md шапка протокола | `787b4ed` |
| ветка | `task/mail-protocol-b18` = `787b4ed` (база main `c100e93`) |
