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
  waits.py add --owe <sid> --what "..." [--by <sid>] [--ttl-minutes N] [--ref R]
  waits.py done <id>            # ожидание снято (ответ получен/отказ)
  waits.py list [--all]
  waits.py overdue              # только просроченные (для inbox-блока)

TTL (Р-075, слово владельца 2026-11-03): единицы — МИНУТЫ.
Дефолт: 5 минут для всех; 10 минут для ses_eceb23a71ffeJO9QnFou8VngZC
(ЦУ, приёмки). Ожидание — веха, не очередь: нет ответа за срок — пинок и
обходной путь, работа не блокируется. Просрочка в минутах = сигнал в inbox
сразу (класс «осечка ожидания»), не через сутки.

Обратная совместимость: старые записи с ttl_hours читаются как
ttl_hours * 60 минут; новые записи хранят ttl_minutes.
Смена состояния (done) — событие, не молчание: строка уходит в done.jsonl.
"""
import argparse
import json
import os
import time

HOME = os.path.expanduser("~/.local/share/ship-mail")
WAITS = os.path.join(HOME, "waits.jsonl")
DONE = os.path.join(HOME, "waits-done.jsonl")
DEFAULT_TTL_MINUTES = 5
CU_TTL_MINUTES = 10
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


def cmd_add(a):
    if getattr(a, "ttl_minutes", 0):
        ttl = int(a.ttl_minutes)
    elif getattr(a, "ttl_hours", 0):
        # обратная совместимость: старый флаг, на входе часы
        ttl = int(a.ttl_hours) * 60
    else:
        ttl = CU_TTL_MINUTES if a.owe == CU_SID else DEFAULT_TTL_MINUTES
    row = {"id": _new_id(),
           "who_waits": a.by or "ses_ece7b76c8ffeOkYZqZe38QbTVx",
           "who_owes": a.owe, "what": a.what, "ref": a.ref or "",
           "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "since_ts": int(time.time()), "ttl_minutes": ttl}
    _append(WAITS, row)
    print(f"WAIT {row['id']}: ждём от {a.owe}: {a.what} (TTL {ttl}м)")


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
    hit[0]["closed"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _append(DONE, hit[0])
    print(f"DONE {wid}: ожидание снято")
    return 0


def _overdue(row):
    age_min = (time.time() - row.get("since_ts", 0)) / 60.0
    return age_min > _ttl_minutes(row), age_min


def _age_label(minutes):
    if minutes >= 120:
        return f"{minutes:.0f}м ({minutes / 60:.1f}ч)"
    return f"{minutes:.0f}м"


def cmd_list(a):
    for r in _rows(WAITS):
        od, age = _overdue(r)
        mark = "ПРОСРОЧЕНО" if od else "в ожидании"
        ttl = _ttl_minutes(r)
        print(f"{r['id']}  {mark} {_age_label(age)}/{ttl}м  "
              f"{r['who_owes'][:20]}…  {r['what'][:60]}")
    return 0


def cmd_overdue(a):
    n = 0
    for r in _rows(WAITS):
        od, age = _overdue(r)
        if od:
            n += 1
            ttl = _ttl_minutes(r)
            print(f"ПРОСРОЧЕНО {r['id']}: {_age_label(age)} > TTL {ttl}м "
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
    a.add_argument("--ttl-minutes", type=int, default=0)
    a.add_argument("--ttl-hours", type=int, default=0,
                   help="устаревший флаг, переводится в минуты")
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
