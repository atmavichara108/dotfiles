#!/usr/bin/env python3
"""mandate_number — журнал номеров мандатов (append-only).

Файл: ~/.local/share/ship-mail/mandate-numbers.jsonl
Строка: {number, from, ts, id} — кто и когда зафиксировал номер мандата.

Правила (Р-090):
  - номер извлекается из письма по шаблону Р-<число>;
  - коллизия номера (два разных письма с одним N) — FAIL с указанием
    существующего и нового id;
  - монотонность: новый номер должен быть больше максимального уже
    зафиксированного, иначе FAIL.

Команды:
  mandate_number.py extract --file <letter>
  mandate_number.py check   --number N --id ID --from SID
  mandate_number.py record  --number N --id ID --from SID
  mandate_number.py show
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

HOME = os.path.expanduser("~/.local/share/ship-mail")
JOURNAL = os.path.join(HOME, "mandate-numbers.jsonl")
NUMBER_RE = re.compile(r"\bР-(\d+)\b")


def _rows(path=JOURNAL):
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def _max_number(rows):
    nums = [int(r.get("number", 0)) for r in rows if str(r.get("number", "")).isdigit()]
    return max(nums) if nums else 0


def cmd_extract(args):
    try:
        text = open(args.file, encoding="utf-8").read()
    except OSError as e:
        print("")
        return 0
    m = NUMBER_RE.search(text)
    print(m.group(1) if m else "")
    return 0


def cmd_check(args):
    rows = _rows()
    same = [r for r in rows if str(r.get("number")) == str(args.number)]
    if same:
        print("FAIL mandate-number: номер %s уже занят письмом %s; новое письмо %s"
              % (args.number, same[0].get("id"), args.id))
        return 2
    mx = _max_number(rows)
    if mx and int(args.number) <= mx:
        print("FAIL mandate-number: номер %s не монотонен (максимум %d)"
              % (args.number, mx))
        return 2
    print("PASS mandate-number: %s свободен" % args.number)
    return 0


def cmd_record(args):
    rows = _rows()
    # на записи те же правила, что и на проверке (fail-closed)
    same = [r for r in rows if str(r.get("number")) == str(args.number)]
    if same:
        print("FAIL mandate-number: номер %s уже занят письмом %s; запись %s отклонена"
              % (args.number, same[0].get("id"), args.id))
        return 2
    mx = _max_number(rows)
    if mx and int(args.number) <= mx:
        print("FAIL mandate-number: номер %s не монотонен (максимум %d)"
              % (args.number, mx))
        return 2
    os.makedirs(os.path.dirname(JOURNAL), exist_ok=True)
    row = {"number": int(args.number), "from": args.frm,
           "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "id": args.id}
    with open(JOURNAL, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("MANDATE-NUMBER %s recorded id=%s" % (args.number, args.id))
    return 0


def cmd_show(args):
    rows = _rows()
    print("записей: %d, максимум: %d" % (len(rows), _max_number(rows)))
    for r in rows[-20:]:
        print("%-6s %s %s %s" % (r.get("number"), r.get("from"),
                                r.get("ts"), r.get("id")))
    return 0


def main():
    ap = argparse.ArgumentParser(prog="mandate_number")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--file", required=True)
    c = sub.add_parser("check")
    c.add_argument("--number", required=True)
    c.add_argument("--id", required=True)
    c.add_argument("--from", dest="frm", required=True)
    r = sub.add_parser("record")
    r.add_argument("--number", required=True)
    r.add_argument("--id", required=True)
    r.add_argument("--from", dest="frm", required=True)
    sub.add_parser("show")
    a = ap.parse_args()
    if a.cmd == "extract":
        return cmd_extract(a)
    if a.cmd == "check":
        return cmd_check(a)
    if a.cmd == "record":
        return cmd_record(a)
    return cmd_show(a)


if __name__ == "__main__":
    raise SystemExit(main())
