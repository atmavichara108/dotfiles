#!/usr/bin/env python3
"""Журнал исполненных команд (ступень 0 программы экономии, канон Р-115).

Код: cmdlog.py record|norm|top|stats
Запись: append-only ~/.local/state/opencode/cmdlog/commands.jsonl
Поля: sid (сессия-исполнитель), ts, cwd, cmd (текст), rc, ms, tokens (если известны)
Нормализация: адреса сессий → <SID>, ветки/хеши git → <GITREF>, пути → <PATH>,
      ISO-даты → <TS>, числа-идентификаторы → <ID>. Повторы считаются по
      нормализованной форме — совпадение без модели, точное и безопасное.
СТУПЕНЬ 1 (без модели): top — верх нормализованных форм по числу повторов.
Модель подключается позже (ступени 2-3) и только поверх журнала.
"""
import argparse
import hashlib
import json
import os
import re
import time

HOME = os.path.expanduser("~/.local/state/opencode/cmdlog")
LOG = os.path.join(HOME, "commands.jsonl")

SID_RE = re.compile(r"\bses_[A-Za-z0-9]{10,}\b")
HEX40_RE = re.compile(r"\b[0-9a-f]{40}\b")
HEX12_RE = re.compile(r"\b[0-9a-f]{7,12}\b")
ISO_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?\b")
WAITID_RE = re.compile(r"\b[a-f0-9]{8}\b")
PATH_RE = re.compile(r"(/home/rudra|~/dotfiles|~)[\w./-]*")
NUM_RE = re.compile(r"\b\d{3,}\b")


def _rows():
    if not os.path.exists(LOG):
        return []
    out = []
    for line in open(LOG, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _norm(cmd):
    s = SID_RE.sub("<SID>", cmd)
    s = ISO_RE.sub("<TS>", s)
    s = HEX40_RE.sub("<GITREF>", s)
    s = HEX12_RE.sub("<REF>", s)
    s = WAITID_RE.sub("<ID>", s)
    s = PATH_RE.sub("<PATH>", s)
    s = NUM_RE.sub("<N>", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def cmd_record(a):
    text = a.cmd
    if a.file:
        text = open(a.file, encoding="utf-8").read().strip()
    if not text:
        print("cmdlog: пустая команда — не записано")
        return 1
    row = {"sid": a.sid, "ts": a.ts or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "cwd": a.cwd or "", "cmd": text, "rc": a.rc, "ms": a.ms, "tokens": a.tokens}
    os.makedirs(HOME, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"CMDLOG {a.sid} rc={a.rc} {len(text)} символов")
    return 0


def cmd_norm(a):
    rows = _rows()
    if a.sid:
        rows = [r for r in rows if r.get("sid") == a.sid]
    print("нормализованные формы (верх):")
    counts = {}
    for r in rows:
        n = _norm(r.get("cmd", ""))
        counts[n] = counts.get(n, 0) + 1
    for form, n in sorted(counts.items(), key=lambda kv: -kv[1])[:a.limit]:
        print(f"  x{n}  {form[:150]}")
    return 0


def cmd_top(a):
    rows = _rows()
    if a.sid:
        rows = [r for r in rows if r.get("sid") == a.sid]
    if a.since:
        cutoff = time.time() - a.since * 86400
        rows = [r for r in rows if _ts(r.get("ts", "")) >= cutoff]
    counts = {}
    for r in rows:
        n = _norm(r.get("cmd", ""))
        if n not in counts:
            counts[n] = {"n": 0, "rcs": {}, "example": r.get("cmd", "")}
        counts[n]["n"] += 1
        rc = r.get("rc")
        counts[n]["rcs"][str(rc)] = counts[n]["rcs"].get(str(rc), 0) + 1
    print(f"ЖУРНАЛ: {len(rows)} команд, {len(counts)} форм")
    for form, d in sorted(counts.items(), key=lambda kv: -kv[1]["n"])[:a.limit]:
        rcs = ",".join(f"{k}:{v}" for k, v in d["rcs"].items())
        print(f"x{d['n']:<3} rc[{rcs}]  {form[:130]}")
        print(f"      пример: {d['example'][:130]}")
    return 0


ADOPT_LOG = os.path.join(HOME, "template-adoptions.jsonl")


def cmd_adopt(a):
    """Журнал принятия шаблона (условие ступени 4, ЦУ ic-app1-and-stage4).

    Append-only: кто, когда, какой шаблон. Дописываемо, не перезаписываем.
    """
    rec = {"op": "adopt", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "by": a.by, "template": a.template}
    os.makedirs(HOME, exist_ok=True)
    with open(ADOPT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"ADOPT {a.by}: {a.template}")
    return 0


def _ts(s):
    try:
        import datetime
        return datetime.datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError):
        return 0.0


def cmd_stats(a):
    rows = _rows()
    bysid = {}
    for r in rows:
        bysid[r.get("sid", "?")] = bysid.get(r.get("sid", "?"), 0) + 1
    print(f"всего команд: {len(rows)}, сессий: {len(bysid)}")

    for sid, n in sorted(bysid.items(), key=lambda kv: -kv[1])[:a.limit]:
        print(f"  {sid}: {n}")
    return 0


TOKEN_PATH = os.path.expanduser(  # secrets-scan:allow (имя переменной содержит token)
    "~/Projects/OpenCode-Vault/control-plane/telemetry/token-budget.jsonl")
FEED_WM = os.path.join(HOME, ".tokens-fed")


def _day(ts_s):
    import datetime
    return datetime.datetime.fromtimestamp(float(ts_s)).strftime("%Y-%m-%d")


def _read_from(watermark):
    """Читает журнал с байтового смещения, доводя до границы строки."""
    if not os.path.exists(LOG):
        return [], os.path.getsize(LOG) if os.path.exists(LOG) else 0
    size = os.path.getsize(LOG)
    if watermark >= size:
        return [], size
    with open(LOG, "rb") as f:
        f.seek(watermark)
        if watermark > 0:  # смещение могло встать посередине строки — доводим до 

            chunk = f.read(1)
            while chunk and chunk != b"\n":
                chunk = f.read(1)
        tail = f.read()
    rows = []
    for line in tail.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows, size


def cmd_tokens(a):
    """Ступень 1 экономии: токены из журнала (первичная правда, ЦУ ic-stage1-verdict).

    Без флагов — срез по дням. --feed — идемпотентная подача в счётчик
    token-budget.jsonl: порции по (сессия, день), только новые, водяной знак
    хранится байтовым смещением. Повторный запуск ничего не добавляет.
    """
    if a.feed:
        try:
            wm = int(open(FEED_WM, encoding="utf-8").read().strip() or 0)
        except (OSError, ValueError):
            wm = 0
        rows, size = _read_from(wm)
        agg = {}
        for r in rows:
            t = r.get("tokens")
            if not t:
                continue
            key = (r.get("sid", "?"), _day(_ts(r.get("ts", ""))))
            agg[key] = agg.get(key, 0) + int(t)
        if not agg:
            with open(FEED_WM, "w", encoding="utf-8") as w:
                w.write(str(size))
            print("tokens-feed: новых порций нет (водяной знак на конце)")
            return 0
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        fed = 0
        with open(TOKEN_PATH, "a", encoding="utf-8") as out:
            for (sid, day), total in sorted(agg.items()):
                rec = {"op": "record", "session_id": sid, "period": "day", "day": day,
                       "input_tokens": total, "output_tokens": 0,
                       "estimated": True, "source": "cmdlog",
                       "model": "journal-aggregate"}
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fed += 1
        with open(FEED_WM, "w", encoding="utf-8") as w:
            w.write(str(size))
        print(f"tokens-feed: подано записей — {fed} (порции по дню/сессии)")
        return 0
    agg = {}
    for r in _rows():
        t = r.get("tokens")
        if not t:
            continue
        day = _day(_ts(r.get("ts", "")))
        agg[day] = agg.get(day, 0) + int(t)
    print("ЖУРНАЛ-ТОКЕНЫ: по дням (поле tokens команд, оценки следов)")
    for day in sorted(agg)[-a.limit:]:
        print(f"  {day}: {agg[day]}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Журнал команд (ступень 0, канон Р-115)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--sid", required=True)
    r.add_argument("--cmd")
    r.add_argument("--file")
    r.add_argument("--cwd")
    r.add_argument("--rc", type=int, default=0)
    r.add_argument("--ms", type=int)
    r.add_argument("--tokens", type=int)
    r.add_argument("--ts")
    n = sub.add_parser("norm")
    n.add_argument("--sid")
    n.add_argument("--limit", type=int, default=20)
    t = sub.add_parser("top")
    t.add_argument("--sid")
    t.add_argument("--limit", type=int, default=20)
    t.add_argument("--since", type=float, help="дней")
    s = sub.add_parser("stats")
    s.add_argument("--limit", type=int, default=10)
    tt = sub.add_parser("tokens")
    tt.add_argument("--feed", action="store_true")
    tt.add_argument("--limit", type=int, default=14)
    ad = sub.add_parser("adopt")
    ad.add_argument("--template", required=True, help="имя/текст шаблона")
    ad.add_argument("--by", default=os.environ.get("OPENCODE_SID", "?"), help="кто принял")
    a = ap.parse_args()
    cmds = {"record": cmd_record, "norm": cmd_norm, "top": cmd_top,
            "stats": cmd_stats, "tokens": cmd_tokens, "adopt": cmd_adopt}
    return cmds[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
