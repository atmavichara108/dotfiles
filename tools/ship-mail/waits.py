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
  waits.py add --owe <sid> --what "..." [--by <sid>] [--ttl-hours N] [--ref R]
  waits.py done <id>            # ожидание снято (ответ получен/отказ)
  waits.py list [--all]
  waits.py overdue              # только просроченные (для inbox-блока)
TTL: 48 ч по умолчанию; для ses_eceb23a71ffeJO9QnFou8VngZC (ЦУ, приёмки) — 72 ч.
Смена состояния (done) — событие, не молчание: строка уходит в done.jsonl.
"""
import argparse
import json
import os
import time

HOME = os.path.expanduser("~/.local/share/ship-mail")
WAITS = os.path.join(HOME, "waits.jsonl")
DONE = os.path.join(HOME, "waits-done.jsonl")
DEFAULT_TTL = 48
CU_SID = "ses_eceb23a71ffeJO9QnFou8VngZC"  # приёмки ЦУ — удлинённый TTL


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


def cmd_add(a):
    ttl = a.ttl_hours or (72 if a.owe == CU_SID else DEFAULT_TTL)
    row = {"id": "%08x" % (int(time.time() * 1000) % (16 ** 8)),
           "who_waits": a.by or "ses_ece7b76c8ffeOkYZqZe38QbTVx",
           "who_owes": a.owe, "what": a.what, "ref": a.ref or "",
           "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "since_ts": int(time.time()), "ttl_hours": ttl}
    _append(WAITS, row)
    print(f"WAIT {row['id']}: ждём от {a.owe}: {a.what} (TTL {ttl}ч)")


def cmd_done(wid):
    rows = _rows(WAITS)
    hit = [r for r in rows if r.get("id") == wid]
    if not hit:
        print(f"waits: ожидание {wid} не найдено")
        return 1
    rest = [r for r in rows if r.get("id") != wid]
    with open(WAITS, "w", encoding="utf-8") as f:
        for r in rest:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    hit[0]["closed"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _append(DONE, hit[0])
    print(f"DONE {wid}: ожидание снято")
    return 0


def _overdue(row):
    age_h = (time.time() - row.get("since_ts", 0)) / 3600.0
    return age_h > row.get("ttl_hours", DEFAULT_TTL), age_h


def cmd_list(a):
    for r in _rows(WAITS):
        od, age = _overdue(r)
        mark = "ПРОСРОЧЕНО" if od else "в ожидании"
        print(f"{r['id']}  {mark} {age:.0f}/{r.get('ttl_hours')}ч  "
              f"{r['who_owes'][:20]}…  {r['what'][:60]}")
    return 0


def cmd_overdue(a):
    n = 0
    for r in _rows(WAITS):
        od, age = _overdue(r)
        if od:
            n += 1
            print(f"ПРОСРОЧЕНО {r['id']}: {age:.0f}ч > TTL {r.get('ttl_hours')}ч "
                  f"| ждём от {r['who_owes'][:20]}… | {r['what'][:70]}")
    print(f"WAITS-OVERDUE {n}")
    return 0


def main():
    p = argparse.ArgumentParser(prog="waits")
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("add")
    a.add_argument("--owe", required=True)
    a.add_argument("--what", required=True)
    a.add_argument("--by", default="")
    a.add_argument("--ttl-hours", type=int, default=0)
    a.add_argument("--ref", default="")
    d = sub.add_parser("done")
    d.add_argument("wid")
    sub.add_parser("list")
    sub.add_parser("overdue")
    args = p.parse_args()
    if args.cmd == "add":
        cmd_add(args)
    elif args.cmd == "done":
        return cmd_done(args.wid)
    elif args.cmd == "overdue":
        return cmd_overdue(args)
    else:
        return cmd_list(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
