#!/usr/bin/env python3
"""waits — реестр осознанных ожиданий (задача «активное ожидание», слово
владельца 2026-10-27,via ИПТ).

Проблема (словом владельца): «нужно ждать осознанно, а я заметил, что это
зачастую пустые ожидания, которые тянутся днями, пока я не напишу». Решение:
ждём не молча, а записью. Каждая постановка «жду от X — Y» — строка в
append-only реестре; TTL просрочки превращает пустое ожидание в дефект
(класс «осечка ожидания»), а inbox каждый ход показывает просроченное.

Файл: ~/.local/share/ship-mail/waits.jsonl (рядом с почтой).
Команды:
  waits.py add --owe <sid> --what "..." [--by <sid>] [--ttl-minutes N]
               [--deadline-minutes N] [--ref R]
               [--type mandate|question|acceptance|pilot|external|proposal]
               [--state S] [--return-condition TEXT]
  waits.py done <id>            # ожидание снято (ответ получен/отказ)
  waits.py stitch <id> --reply-to <file|id> --answered-by <sid> \
              --answered-at <ISO> [--evidence TEXT]  # пришить ответ (Р-092)
  waits.py stitch-report        # ответы без пришивки (lag N), вне блока просрочки
  waits.py sweep [--ping]       # ответ есть -> stitch; нет ответа -> ping/escalate
  waits.py ping <id>            # пинок: каденс TTL удваивается (backoff до срока)
  waits.py list [--all]
  waits.py overdue              # только просроченные (для inbox-блока)

Схема (решение ЦУ 2026-11-04, развитие механизма, не канон):
  type — mandate (default), question, acceptance, pilot, external, proposal;
  state — open (default), closed, rejected; proposal по умолчанию rejected;
  return_condition — что должно произойти, чтобы ожидание закрылось.
  Старые записи без type/state читаются как mandate/open.

TTL (Р-075, слово владельца 2026-11-03): единицы — МИНУТЫ.
Дефолт: 5 минут для всех; 10 минут для ses_eceb23a71ffeJO9QnFou8VngZC
(ЦУ, приёмки).

Модель (уточнение ЦУ 2026-11-03): TTL — это КАДЕНС пинка, а не дефект.
Срок/дедлайн живёт в тексте `what` (например, «до 04.11 утра») или в
необязательном `deadline_minutes`. Просрочка = пинок: работа идёт без
блокировки, `ping <id>` удваивает каденс (но не выше deadline_minutes,
если он задан). В overdue такие записи помечаются «пинок, не дефект».

Обратная совместимость: старые записи с ttl_hours читаются как
ttl_hours * 60 минут; новые записи хранят ttl_minutes.
Смена состояния (done) — событие, не молчание: строка уходит в done.jsonl.
"""
import argparse
import json
import os
import re
import time

HOME = os.path.expanduser("~/.local/share/ship-mail")
WAITS = os.path.join(HOME, "waits.jsonl")
DONE = os.path.join(HOME, "waits-done.jsonl")
DEFAULT_TTL_MINUTES = 5
CU_TTL_MINUTES = 10
CU_SID = "ses_eceb23a71ffeJO9QnFou8VngZC"  # приёмки ЦУ — удлинённый TTL

# Схема ожиданий (решение ЦУ 2026-11-04, по ответу ИПТ через ЦСПМ):
# тип + состояние + условие возврата. Старые записи читаются как mandate/open.
WAIT_TYPES = ("mandate", "question", "acceptance", "pilot", "external", "proposal")
DEFAULT_TYPE = "mandate"
DEFAULT_STATE = "open"


def _rows(path):
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    return out


def _append(path, row):
    os.makedirs(HOME, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _wid(row):
    return row.get("id") or "%08x" % abs(hash(json.dumps(
        row, sort_keys=True, ensure_ascii=False)) % (16 ** 8))


def _new_id():
    # уникальность: ms-метка + суффикс при коллизии (дефект 1: два add
    # в одну миллисекунду давали одинаковый id)
    base = int(time.time() * 1000) % (16 ** 8)
    existing = {r.get("id") for r in _rows(WAITS)} | {r.get("id") for r in _rows(DONE)}
    for n in range(4096):
        wid = "%08x" % ((base + n) % (16 ** 8))
        if wid not in existing:
            return wid
    raise SystemExit("waits: не удалось сгенерировать уникальный id")


def _ttl_minutes(row):
    """TTL строки в минутах; старые ttl_hours читаются как часы*60."""
    if row.get("ttl_minutes") is not None:
        return max(0, int(row["ttl_minutes"]))
    if row.get("ttl_hours") is not None:
        return max(0, int(row["ttl_hours"]) * 60)
    return DEFAULT_TTL_MINUTES


def _type(row):
    return row.get("type") or DEFAULT_TYPE


def _state(row):
    if row.get("state"):
        return row["state"]
    return "rejected" if _type(row) == "proposal" else DEFAULT_STATE


_DEADLINE_RE = re.compile(
    r"(до\s+\d{1,2}[./]\d{1,2}|\bдедлайн\b|\bсрок\b|\bутра\b|\bвечера\b|\b\d{1,2}:\d{2}\b)",
    re.IGNORECASE,
)


def _has_deadline(row):
    """Есть ли у ожидания срок/дедлайн, отличный от каденса пинка."""
    if row.get("deadline_minutes") is not None:
        return True
    if row.get("deadline"):
        return True
    return bool(_DEADLINE_RE.search(str(row.get("what", ""))))


def _rewrite_rows(rows):
    with open(WAITS, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def cmd_add(a):
    if getattr(a, "ttl_minutes", 0):
        ttl = int(a.ttl_minutes)
    elif getattr(a, "ttl_hours", 0):
        # обратная совместимость: старый флаг, на входе часы
        ttl = int(a.ttl_hours) * 60
    else:
        ttl = CU_TTL_MINUTES if a.owe == CU_SID else DEFAULT_TTL_MINUTES
    wtype = getattr(a, "type", None) or DEFAULT_TYPE
    state = getattr(a, "state", "") or ("rejected" if wtype == "proposal" else DEFAULT_STATE)
    row = {"id": _new_id(),
           "who_waits": a.by or "ses_ece7b76c8ffeOkYZqZe38QbTVx",
           "who_owes": a.owe, "what": a.what, "ref": a.ref or "",
           "type": wtype, "state": state,
           "return_condition": getattr(a, "return_condition", "") or "",
           "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "since_ts": int(time.time()), "ttl_minutes": ttl}
    if getattr(a, "deadline_minutes", 0):
        row["deadline_minutes"] = int(a.deadline_minutes)
    _append(WAITS, row)
    extra = f", дедлайн {row['deadline_minutes']}м" if "deadline_minutes" in row else ""
    print(f"WAIT {row['id']} [{wtype}/{state}]: ждём от {a.owe}: {a.what} (TTL {ttl}м{extra})")


def cmd_done(wid):
    rows = _rows(WAITS)
    hit = [r for r in rows if r.get("id") == wid]
    if not hit:
        # id нет в активных: возможно, уже закрыт раньше (повторный done) —
        # честный ответ вместо «не найдено» (дефект 1, ИЦ 2026-10-31)
        closed = [r for r in _rows(DONE) if r.get("id") == wid]
        if closed:
            print(f"waits: ожидание {wid} уже закрыто "
                  f"({closed[0].get('closed', '?')}) — повтор не нужен")
            return 0
        print(f"waits: ожидание {wid} не найдено")
        return 1
    rest = [r for r in rows if r.get("id") != wid]
    with open(WAITS, "w", encoding="utf-8") as f:
        for r in rest:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    hit[0]["state"] = "closed"
    hit[0]["closed"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _append(DONE, hit[0])
    print(f"DONE {wid}: ожидание снято")
    return 0


def cmd_ping(wid):
    """Пинок: каденс удваивается, но не выше дедлайна (если он задан)."""
    rows = _rows(WAITS)
    hit = [r for r in rows if r.get("id") == wid]
    if not hit:
        print(f"waits: ожидание {wid} не найдено")
        return 1
    row = hit[0]
    old = _ttl_minutes(row)
    new = old * 2
    dl = row.get("deadline_minutes")
    if dl is not None:
        new = min(new, max(0, int(dl)))
    # не плодим zero-каденс
    new = max(1, new)
    row["ttl_minutes"] = new
    row["pinged"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    row["ping_count"] = int(row.get("ping_count", 0)) + 1
    _rewrite_rows(rows)
    print(f"PING {wid}: TTL {old}м -> {new}м (пинок, не дефект)")
    return 0


def _parse_ts(value):
    """ISO-строка -> epoch; сбой -> None (не выдумываем лаг)."""
    if not value:
        return None
    try:
        import datetime as _dt
        raw = str(value).strip()
        # допускаем Z и +03:00: datetime.fromisoformat Z не ест в 3.10-
        raw = raw.replace("Z", "+00:00")
        dt = _dt.datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        return dt.timestamp()
    except Exception:  # noqa: BLE001
        return None


def _overdue(row):
    age_min = (time.time() - row.get("since_ts", 0)) / 60.0
    if _type(row) == "proposal" or _state(row) != "open":
        return False, age_min
    return age_min > _ttl_minutes(row), age_min


def cmd_stitch(a):
    """Пришить ответ: ответ есть, но wait ещё открыт.

    Append-only строка в waits-done:
      op=stitch, reply_to, answered_by, answered_at, stitched_at,
      lag_minutes, evidence, state=answered.
    """
    rows = _rows(WAITS)
    hit = [r for r in rows if r.get("id") == a.wid]
    if not hit:
        done = [r for r in _rows(DONE) if r.get("id") == a.wid]
        if done:
            print(f"waits: ожидание {a.wid} уже закрыто "
                  f"({done[0].get('state', '?')}) — повтор не нужен")
            return 0
        print(f"waits: ожидание {a.wid} не найдено")
        return 1
    row = hit[0]
    answered_ts = _parse_ts(a.answered_at)
    if answered_ts is None:
        print(f"waits: не разбираю answered_at={a.answered_at!r} — формат ISO")
        return 2
    since_ts = int(row.get("since_ts") or int(time.time()))
    lag_min = round((answered_ts - since_ts) / 60.0, 1)
    stitched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    row.update({
        "op": "stitch",
        "reply_to": a.reply_to or "",
        "answered_by": a.answered_by or "",
        "answered_at": a.answered_at,
        "stitched_at": stitched_at,
        "lag_minutes": lag_min,
        "evidence": a.evidence or "",
        "state": "answered",
        "closed": stitched_at,
        "op_deadline_minutes": 24 * 60,
        "sweep_lag_defect": lag_min > 60,
    })
    rest = [r for r in rows if r.get("id") != a.wid]
    _rewrite_rows(rest)
    _append(DONE, row)
    print(f"STITCH {a.wid}: ответ пришит, lag {lag_min}м "
          f"(from {row.get('who_owes')}, reply_to {row.get('reply_to')})")
    if lag_min > 60:
        print(f"SWEEP LAG-DEFECT {a.wid}: lag {lag_min}м > 60м "
              f"(дефект детектора, Р-093)")
    return 0


def cmd_stitch_report(_a=None):
    """Строчки «ответ без пришивки»: stitch-closed вне блока просрочки."""
    n = 0
    now = time.time()
    for r in _rows(DONE):
        if r.get("op") != "stitch" or _state(r) != "answered":
            continue
        stitched_ts = _parse_ts(r.get("stitched_at"))
        if stitched_ts is None:
            continue
        deadline = r.get("op_deadline_minutes") or 24 * 60
        try:
            deadline = int(deadline)
        except Exception:
            deadline = 24 * 60
        age_minutes = (now - stitched_ts) / 60.0
        if age_minutes >= deadline:
            continue
        n += 1
        print(f"ОТВЕТ БЕЗ ПРИШИВКИ (lag {r.get('lag_minutes')}м) {r.get('id')} "
              f"| ответил {r.get('answered_by')} | reply_to {r.get('reply_to')} "
              f"| {str(r.get('what'))[:60]}")
    print(f"STITCH-REPORT {n}")
    return 0


def _reply_files(sid):
    base = os.path.join(HOME, "inbox", sid)
    out = []
    for d in (base, os.path.join(base, "read")):
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(".md"):
                out.append(os.path.join(d, name))
    return out


def _frontmatter(path):
    data = {}
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return data
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return data
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        data[k.strip()] = v.strip().strip('"')
    return data


def _detect_reply(row):
    """Есть ли ответ: письмо от who_owes в ящик who_waits не ранее since."""
    since = int(row.get("since_ts") or 0)
    owe = row.get("who_owes") or ""
    waiter = row.get("who_waits") or ""
    for f in _reply_files(waiter):
        meta = _frontmatter(f)
        if meta.get("from") != owe:
            continue
        ts = _parse_ts(meta.get("ts"))
        if ts is None or ts < since:
            continue
        return meta.get("ts"), os.path.basename(f)
    return None, None


def cmd_sweep(a):
    """TTL-sweep: ответ есть -> stitch; ответа нет -> ping/escalate hint."""
    rows = _rows(WAITS)
    for r in rows:
        if _type(r) == "proposal" or _state(r) != "open":
            continue
        answered_at, reply = _detect_reply(r)
        if answered_at:
            class _A:  # простейший аргумент-объект для cmd_stitch
                pass
            args = _A()
            args.wid = r.get("id")
            args.reply_to = reply
            args.answered_by = r.get("who_owes") or ""
            args.answered_at = answered_at
            args.evidence = "auto-sweep: reply found in inbox"
            cmd_stitch(args)
            continue
        od, age = _overdue(r)
        if od:
            if a.ping:
                cmd_ping(r)
            print(f"SWEEP NO-ANSWER {r.get('id')}: {_age_label(age)} без ответа "
                  f"| ping/escalate к {r.get('who_owes')} | {str(r.get('what'))[:60]}")
        else:
            print(f"SWEEP WAITING {r.get('id')}: {_age_label(age)} без ответа, "
                  f"TTL ещё не вышел")
    return 0


def cmd_overdue(a):
    n = 0
    for r in _rows(WAITS):
        od, age = _overdue(r)
        if od:
            n += 1
            ttl = _ttl_minutes(r)
            kind = " (пинок, не дефект; дедлайн в what)" if _has_deadline(r) else ""
            print(f"ПРОСРОЧЕНО {r['id']} [{_type(r)}]: {_age_label(age)} > TTL {ttl}м{kind} "
                  f"| ждём от {r['who_owes']} | {r['what'][:70]}")
    print(f"WAITS-OVERDUE {n}")
    return 0


def _age_label(minutes):
    if minutes >= 120:
        return f"{minutes:.0f}м ({minutes / 60:.1f}ч)"
    return f"{minutes:.0f}м"


def cmd_list(a):
    for r in _rows(WAITS):
        od, age = _overdue(r)
        wtype, state = _type(r), _state(r)
        if wtype == "proposal":
            mark = "предложение"
        elif state != "open":
            mark = state
        else:
            mark = "ПРОСРОЧЕНО" if od else "в ожидании"
            if od and _has_deadline(r):
                mark += " (пинок)"
        ttl = _ttl_minutes(r)
        print(f"{r['id']} [{wtype}/{state}] {mark} {_age_label(age)}/{ttl}м  "
              f"{r['who_owes']}  {r['what'][:60]}")
    return 0


def cmd_overdue(a):
    n = 0
    for r in _rows(WAITS):
        od, age = _overdue(r)
        if od:
            n += 1
            ttl = _ttl_minutes(r)
            kind = " (пинок, не дефект; дедлайн в what)" if _has_deadline(r) else ""
            print(f"ПРОСРОЧЕНО {r['id']} [{_type(r)}]: {_age_label(age)} > TTL {ttl}м{kind} "
                  f"| ждём от {r['who_owes']} | {r['what'][:70]}")
    print(f"WAITS-OVERDUE {n}")
    return 0


def main():
    p = argparse.ArgumentParser(prog="waits")
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("add")
    a.add_argument("--owe", required=True)
    a.add_argument("--what", required=True)
    a.add_argument("--by", default="")
    a.add_argument("--type", choices=WAIT_TYPES, default=DEFAULT_TYPE,
                   help="тип ожидания (default: mandate)")
    a.add_argument("--state", default="",
                   help="состояние (default: open; proposal -> rejected)")
    a.add_argument("--return-condition", default="",
                   help="условие возврата: что должно произойти, чтобы ожидание закрылось")
    a.add_argument("--ttl-minutes", type=int, default=0)
    a.add_argument("--ttl-hours", type=int, default=0,
                   help="устаревший флаг, переводится в минуты")
    a.add_argument("--deadline-minutes", type=int, default=0,
                   help="срок исполнения в минутах от since; ограничивает backoff")
    a.add_argument("--ref", default="")
    d = sub.add_parser("done")
    d.add_argument("wid")
    st = sub.add_parser("stitch")
    st.add_argument("wid")
    st.add_argument("--reply-to", default="")
    st.add_argument("--answered-by", default="")
    st.add_argument("--answered-at", required=True,
                    help="ISO-время ответа (для lag)")
    st.add_argument("--evidence", default="")
    sub.add_parser("stitch-report")
    sw = sub.add_parser("sweep")
    sw.add_argument("--ping", action="store_true",
                    help="на просроченном без ответа — применить пинок TTL")
    pi = sub.add_parser("ping")
    pi.add_argument("wid")
    sub.add_parser("list")
    sub.add_parser("overdue")
    args = p.parse_args()
    if args.cmd == "add":
        cmd_add(args)
    elif args.cmd == "done":
        return cmd_done(args.wid)
    elif args.cmd == "stitch":
        return cmd_stitch(args)
    elif args.cmd == "stitch-report":
        return cmd_stitch_report(args)
    elif args.cmd == "sweep":
        return cmd_sweep(args)
    elif args.cmd == "ping":
        return cmd_ping(args.wid)
    elif args.cmd == "overdue":
        return cmd_overdue(args)
    else:
        return cmd_list(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
