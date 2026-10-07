# Handoff — Sysop → Дирижёр: B22 защита от перехвата HEAD (claim владения веткой)

**Дата:** 2026-10-07
**Ветка:** task/head-guard-b22 (база main=1cab443) — заявлена за sysop через сам механизм
**Автор:** sysop (primary)
**Scope:** B22 — claims.jsonl фиксирует владельца task/*-ветки; pre-commit
проверяет «чья HEAD». Прод-деревья не тронуты.

---

## Механизм

| Компонент | Что делает |
|---|---|
| `hello.sh claim / claim-release` (новые команды) | Записи `op:claim {session, branch, scope, ts, ttl_minutes=240}` / `op:release` в claims.jsonl — **плоскость scope, не доставка** (receipts letter.sh не дублируются). |
| `tools/git-agent/head-guard.sh check` | Резолвер: последняя владельческая запись по ветке (tail = последнее), сравнение с `$OPENCODE_SESSION_ID`. |
| pre-commit **гейт 5** | Вызывает head-guard; обход `HEAD_GUARD_OK=1`. Уже живой — коммиты этого handoff прошли через него. |
| Совместимость | `ping`/`list` игнорируют claim/release-записи (liveness-фолд не тронут — регрессия smoke.sh 15/15). |

## Режим: SOFT-BLOCK (обоснование)

Блокировка **только при конкретных уликах**: на task/*-ветке есть **свежий**
`claim` другой сессии. Ложных срабатываний нет по построению — все
неопознанные случаи дают тихий pass, спорные — WARN + след в журнал
(`~/.local/state/opencode/head-guard.log`, metadata-only):

| Кейс | Исход |
|---|---|
| своя ветка (session == owner) | GO, молча |
| не task/* (main и т.п.) | GO, молча |
| нет claim на ветку (легаси) | GO, молча |
| последний op=release | GO, молча |
| claim протух (> TTL=240 мин) | WARN-журнал, GO |
| исполнитель не опознать (env пуст) | WARN stderr + журнал, GO |
| **чужой свежий claim** | **BLOCK rc=1** + журнал |

Блокировать при неизвестном исполнителе = ломать жизнь человеку в терминале
без доказательств; мягкий след в журнале даёт Дирижёру сигнал без лжи-СТОП. TTL=240
(ветки держат часами; 30-мин TTL hello не годится).

## Приёмка (sandbox `HEAD_GUARD_CLAIMS=/tmp/opencode/b22-sandbox/…`, прод-claims не тронут)

1. чужой claim → `BLOCK … HEAD_GUARD_OK=1` **rc=1** ✓
2. своя ветка → **rc=0** ✓
3. release → **rc=0** ✓
4. main → **rc=0** молча ✓
5. legacy без claim → **rc=0** ✓
6. stale claim → **rc=0** + `stale-claim` в журнале ✓
7. неизвестный исполнитель → **rc=0** + `unknown-executor` в журнале ✓
8. регрессия `smoke.sh` → **15/15 PASS** ✓
9. живой гейт: коммиты `af6e763`/`68433d2` прошли pre-commit с гейтом 5 (своя
   ветка заявлена самими собой через `hello.sh claim`) ✓

## Repro

```bash
cd ~/dotfiles
CL=/tmp/opencode/b22-repro/claims.jsonl; mkdir -p /tmp/opencode/b22-repro
CLAIMS_FILE=$CL bash tools/peer-comms/hello.sh claim --session ses_A --branch task/x-test --scope t
HEAD_GUARD_CLAIMS=$CL bash tools/git-agent/head-guard.sh check --branch task/x-test --session ses_B  # rc=1 BLOCK
HEAD_GUARD_CLAIMS=$CL bash tools/git-agent/head-guard.sh check --branch task/x-test --session ses_A  # rc=0
```

## Артефакты

| Артефакт | SHA |
|---|---|
| head-guard.sh + hello.sh claim/release | `af6e763` |
| pre-commit гейт 5 | `68433d2` |
| handoff | этот коммит |

Формат claims-записи владельца (уточнение по месту, п.1 мандата):
`{"op":"claim","session":"ses_…","branch":"task/…","scope":"…","ts":<epoch>,"ttl_minutes":240}`;
снятие: `{"op":"release","session":"ses_…","branch":"task/…","ts":<epoch>}`.
