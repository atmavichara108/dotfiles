#!/usr/bin/env python3
"""Живое состояние сессии: запись на диск ДО ответа, восстановление ходом.

Канон Р-105 (2026-11-06): важное (слово владельца дословно, решение, доказательство,
открытое ожидание) не держится в контексте как единственная копия — пишется на диск
раньше, чем становится нужным. Compaction (авто или при переходе на модель с меньшим
контекстом) и ручная команда — три способа потерять; защита одна: диск + сверка свежести.

Команды:
  write   --sid <sid> --kind owner-word|decision|evidence|wait|note --text "..."
          [--basis quoted] [--ref ...] [--ts ...]
  append  --sid <sid> --kind ... --file <path>   (длинный текст — файлом)
  bootstrap --sid <sid>     — строка восстановления: цель, слова владельца, открытые ожидания
  flush   --sid <sid>       — снимок состояния + хеш (перед уходом/переключением модели)
  check   --sid <sid>       — свежесть: писать надо или нет (stale → WARN)
"""
import argparse
import hashlib
import json
import os
import time

HOME = os.path.expanduser("~/.local/state/opencode/live-state")
KINDS = ("owner-word", "decision", "evidence", "wait", "note")
STALE_MIN = 15

SID_PREFIX = "ses_"


def _path(sid, name):
    return os.path.join(HOME, sid, name)


def _rows(sid):
    p = _path(sid, "events.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _write_event(sid, row):
    os.makedirs(_path(sid, ""), exist_ok=True)
    p = _path(sid, "events.jsonl")
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return p


def _goal_sidecar(sid):
    for base in (os.path.expanduser("~/.local/state/opencode/goal"),
                 os.path.expanduser("~/.local/state/opencode/goals")):
        p = os.path.join(base, f"{sid}.json")
        if os.path.exists(p):
            try:
                return json.load(open(p, encoding="utf-8"))
            except json.JSONDecodeError:
                return None
    p = os.path.expanduser("~/.local/state/opencode/goal.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def _open_waits():
    p = os.path.expanduser("~/.local/share/ship-mail/waits.jsonl")
    out = []
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("state", "open") == "open":
                out.append(r)
    return out


def cmd_write(a):
    text = a.text
    if a.file:
        text = open(a.file, encoding="utf-8").read().strip()
    if not text:
        print("persist: пустой текст — не записано")
        return 1
    row = {"op": "write", "kind": a.kind, "ts": a.ts or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "sid": a.sid, "text": text}
    if a.basis:
        row["basis"] = a.basis
    if a.ref:
        row["ref"] = a.ref
    _write_event(a.sid, row)
    print(f"PERSIST {a.kind} {a.sid} {len(text)} символов")
    return 0


def cmd_bootstrap(a):
    rows = _rows(a.sid)
    words = [r for r in rows if r.get("kind") == "owner-word"][-5:]
    goal = _goal_sidecar(a.sid)
    waits = [w for w in _open_waits() if w.get("who_owes") == a.sid or w.get("by") == a.sid]
    print("=== ЖИВОЕ СОСТОЯНИЕ СЕССИИ (восстановление после сжатия) ===")
    if goal:
        obj = goal.get("objective") or goal.get("goal") or ""
        crit = goal.get("criteria") or goal.get("criteria_list") or ""
        kill = goal.get("kill") or ""
        print(f"ЦЕЛЬ: {obj}")
        if crit:
            print(f"КРИТЕРИИ: {crit}")
        if kill:
            print(f"ОСТАНОВ: {kill}")
        print(f"WIP: {goal.get('wip', '?')}")
    else:
        print("ЦЕЛЬ: не зафиксирована (сайдкара нет) — перед ходом с работой зафиксируй")
    if words:
        print("СЛОВА ВЛАДЕЛЬЦА (дословно, последние):")
        for w in words:
            print(f"  [{w.get('ts', '?')[:16]}] {w.get('text', '')[:300]}")
    if waits:
        print(f"ОТКРЫТЫЕ ОЖИДАНИЯ СЕССИИ: {len(waits)}")
        for w in waits[:8]:
            print(f"  {w.get('id')} · {w.get('type')} · {str(w.get('what'))[:70]}")
    last = rows[-1]["ts"] if rows else None
    now = time.time()
    if last:
        try:
            import datetime
            t = datetime.datetime.fromisoformat(last)
            age = (now - t.timestamp()) / 60.0
            flag = "СВЕЖЕ" if age <= STALE_MIN else f"УСТАРЕЛО ({age:.0f}м > {STALE_MIN}м) — запиши перед работой"
            print(f"ПОСЛЕДНЯЯ ЗАПИСЬ: {last[:16]} · {flag}")
        except ValueError:
            print(f"ПОСЛЕДНЯЯ ЗАПИСЬ: {last[:16]}")
    else:
        print("ЗАПИСЕЙ НЕТ — записывай важное каждый ход")
    print("=== КОНЕЦ ВОССТАНОВЛЕНИЯ ===")
    return 0


def cmd_flush(a):
    rows = _rows(a.sid)
    goal = _goal_sidecar(a.sid)
    waits = [w for w in _open_waits() if w.get("who_owes") == a.sid or w.get("by") == a.sid]
    snap = {"sid": a.sid, "flushed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "events": len(rows),
            "owner_words": [r for r in rows if r.get("kind") == "owner-word"][-5:],
            "goal": goal, "open_waits": waits,
            "waits_total": len(waits)}
    p = _path(a.sid, "state.json")
    os.makedirs(_path(a.sid, ""), exist_ok=True)
    blob = json.dumps(snap, ensure_ascii=False, indent=1)
    with open(p, "w", encoding="utf-8") as f:
        f.write(blob)
    h = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    with open(_path(a.sid, "state.sha256"), "w", encoding="utf-8") as f:
        f.write(h + "\n")
    print(f"FLUSH {a.sid}: снимок state.json ({len(rows)} событий, {len(waits)} ожиданий) sha256:{h}")
    return 0


def cmd_check(a):
    rows = _rows(a.sid)
    if not rows:
        print(f"CHECK {a.sid}: ЗАПИСЕЙ НЕТ — запиши важное этим ходом (stale)")
        return 2
    import datetime
    last = rows[-1]["ts"]
    try:
        age = (time.time() - datetime.datetime.fromisoformat(last).timestamp()) / 60.0
    except ValueError:
        print(f"CHECK {a.sid}: время последней записи не читается — перезапиши")
        return 2
    if age > STALE_MIN:
        print(f"CHECK {a.sid}: УСТАРЕЛО {age:.0f}м > {STALE_MIN}м — записывай перед работой/уходом")
        return 2
    print(f"CHECK {a.sid}: свеже {age:.0f}м (порог {STALE_MIN}м)")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Живое состояние сессии (запись на диск до ответа)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write")
    w.add_argument("--sid", required=True)
    w.add_argument("--kind", required=True, choices=KINDS)
    w.add_argument("--text")
    w.add_argument("--file")
    w.add_argument("--basis", choices=["quoted", "paraphrase"])
    w.add_argument("--ref")
    w.add_argument("--ts")

    ap_ = sub.add_parser("append")
    ap_.add_argument("--sid", required=True)
    ap_.add_argument("--kind", required=True, choices=KINDS)
    ap_.add_argument("--file", required=True)
    ap_.add_argument("--basis", choices=["quoted", "paraphrase"])
    ap_.add_argument("--ref")
    ap_.add_argument("--ts")

    b = sub.add_parser("bootstrap")
    b.add_argument("--sid", required=True)

    f = sub.add_parser("flush")
    f.add_argument("--sid", required=True)

    c = sub.add_parser("check")
    c.add_argument("--sid", required=True)

    a = ap.parse_args()
    if a.cmd in ("write", "append"):
        return cmd_write(a)
    if a.cmd == "bootstrap":
        return cmd_bootstrap(a)
    if a.cmd == "flush":
        return cmd_flush(a)
    if a.cmd == "check":
        return cmd_check(a)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
