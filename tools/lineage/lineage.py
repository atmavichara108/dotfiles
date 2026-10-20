#!/usr/bin/env python3
"""lineage.py — git-слой И-53 (ADR-028 v2): ledger (flock, append-only) + аудит.

Субкоманды:
  append  — запись в канонический ledger ~/.local/state/opencode/lineage/ledger.jsonl
            (паттерны ADR: fact | revision; всё под flock; никогда не редактирует).
  audit   — read-only сшивка источников (session_v2, git refs/config, worktrees,
            receipts) → чистый отчёт или список тикетов. НИКОГДА не пишет в БД.

Углеродные инварианты ADR-028: сирота не отбрасывается (orphan:true);
ledger не дублирует БД — только связки/события источников; шесть реестров
не удаляются. Выход: человекочитаемый отчёт + --json для машин.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
LEDGER = Path(os.environ.get("LINEAGE_LEDGER",
                              HOME / ".local/state/opencode/lineage/ledger.jsonl"))
DB = HOME / ".local/share/opencode/opencode.db"
REPO = Path(os.environ.get("LINEAGE_REPO", HOME / "dotfiles"))
RECEIPTS_OUT = HOME / ".local/state/opencode/mail/receipts-out.jsonl"
STALE_DAYS = 2
UNPROCESSED_H = 48


def sh(args, cwd=None):
    return subprocess.run(args, cwd=cwd or REPO, capture_output=True,
                          text=True).stdout


def last_rev(session_id):
    """Последняя ревизия session_id в ledger (0 — если нет). Состояние = последняя ревизия."""
    rev = 0
    try:
        with open(LEDGER) as f:
            for l in f:
                try:
                    d = json.loads(l)
                except json.JSONDecodeError:
                    continue
                if d.get("kind") == "revision" and d.get("session_id") == session_id:
                    rev = max(rev, int(d.get("rev", 0)))
    except FileNotFoundError:
        pass
    return rev


def cmd_append(a):
    rec = {"ts": int(time.time()), "kind": a.kind, "session_id": a.session_id}
    for k in ("branch", "worktree", "task", "pr", "status", "stage", "via",
              "ref", "edge", "repo", "note"):
        v = getattr(a, k, None)
        if v is not None:
            rec[k] = v
    if a.kind not in ("fact", "revision"):
        sys.exit("kind: fact|revision")
    if a.kind == "revision" and a.session_id:
        rec["rev"] = last_rev(a.session_id) + 1   # revise_status: rev-цепочка
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    fresh = not LEDGER.exists()
    line = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
    with open(LEDGER, "a") as f:            # append-only, длина записи > pipe
        fcntl.flock(f, fcntl.LOCK_EX)       # буфера — только flock (ADR §5)
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())
    if fresh:
        os.chmod(LEDGER, 0o600)             # R1: права 600 на канонический ledger
    print(line)
    return 0


def cmd_status(a):
    """Состояние session_id = последняя ревизия (revise_status-читатель)."""
    rows = []
    try:
        with open(LEDGER) as f:
            for l in f:
                try:
                    d = json.loads(l)
                except json.JSONDecodeError:
                    continue
                if d.get("session_id") == a.session_id:
                    rows.append(d)
    except FileNotFoundError:
        pass
    revs = [r for r in rows if r.get("kind") == "revision"]
    latest = sorted(revs, key=lambda r: int(r.get("rev", 0)))[-1] if revs else None
    if latest:
        print(json.dumps(latest, ensure_ascii=False))
    else:
        print("(нет ревизий)" if a.session_id else "(не задан session-id)")
        return 1
    return 0


def db_rows(sql):
    if not DB.exists():
        return []
    con = sqlite3.connect(f"file:{DB}?mode=ro&immutable=0", uri=True)
    try:
        return con.execute(sql).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()


def audit_sessions():
    total = db_rows("SELECT COUNT(*) FROM session_v2")[0][0]
    orphans = db_rows("SELECT COUNT(*) FROM session_v2 WHERE parent_id IS NULL "
                      "AND fork_session_id IS NULL")[0][0]
    edges = {
        "child-of(parent)": db_rows("SELECT COUNT(*) FROM session_v2 WHERE parent_id IS NOT NULL")[0][0],
        "forked-from": db_rows("SELECT COUNT(*) FROM session_v2 WHERE fork_session_id IS NOT NULL")[0][0],
    }
    return {"total": total, "orphan": orphans, "edges": edges}


def audit_branches():
    refs = sh(["git", "for-each-ref", "--format=%(refname:short)\t%(committerdate:unix)",
               "refs/heads/task/"]).splitlines()
    now = time.time()
    out = {"total": 0, "with_owner": 0, "orphan": [], "stale": []}
    for line in refs:
        if not line.strip():
            continue
        name, ts = line.split("\t")
        out["total"] += 1
        owner = sh(["git", "config", "--get", f"branch.{name}.owner"]).strip()
        if owner:
            out["with_owner"] += 1
        else:
            out["orphan"].append(name)
        in_main = subprocess.run(["git", "merge-base", "--is-ancestor", name, "origin/main"],
                                 cwd=REPO, capture_output=True).returncode == 0
        if not in_main and (now - int(ts)) / 86400 >= STALE_DAYS:
            out["stale"].append({"branch": name, "age_d": round((now - int(ts)) / 86400, 1)})
    return out


def audit_worktrees():
    wt = sh(["git", "worktree", "list"]).strip().splitlines()
    return {"count": len(wt), "paths": [l.split()[0] for l in wt][1:]}


def audit_letters():
    """Слой 3: sent → delivered → processed. processed = finished/started receipt
    с тем же ref ОТ КОНТРАГЕНТА (в наших исходящих — наших finished на тот же ref)."""
    if not RECEIPTS_OUT.exists():
        return {"scanned": 0, "unprocessed": []}
    now = time.time()
    by_ref: dict = {}
    n = 0
    with open(RECEIPTS_OUT) as f:
        for l in f:
            try:
                d = json.loads(l)
            except json.JSONDecodeError:
                continue
            n += 1
            ref = d.get("ref") or d.get("scope") or "?"
            e = by_ref.setdefault(ref, {"sent_ts": now, "answered": False,
                                        "to": d.get("to", "")})
            e["sent_ts"] = min(e["sent_ts"], d.get("ts", now))
            if str(d.get("receipt", "")) in ("started", "finished") and d.get("from"):
                e["answered"] = True
            if d.get("scope", "").endswith("-ack") or "receipt" in str(d.get("scope", "")):
                pass
    stale = [{"ref": r, "age_h": round((now - e["sent_ts"]) / 3600, 1), "to": e["to"]}
             for r, e in by_ref.items()
             if not e["answered"] and (now - e["sent_ts"]) / 3600 > UNPROCESSED_H]
    return {"scanned": n, "refs": len(by_ref), "unprocessed": stale}


def cmd_audit(a):
    rep = {
        "ts": int(time.time()),
        "sessions": audit_sessions() if DB.exists() else None,
        "branches": audit_branches(),
        "worktrees": audit_worktrees(),
        "letters": audit_letters(),
    }
    tickets = []
    if rep["sessions"]:
        if rep["sessions"]["orphan"] > 0:
            tickets.append(f"S1: {rep['sessions']['orphan']} безродных сессий "
                           f"(списать в ledger orphan:true / tgs-bridge задача)")
    if rep["branches"]["orphan"]:
        tickets.append(f"S2: {len(rep['branches']['orphan'])} task-веток без owner "
                       f"(claim в ledger, branch.*.owner dual-write)")
    for s in rep["branches"]["stale"]:
        tickets.append(f"S3: stale {s['branch']} ({s['age_d']}д) — close/merge")
    for l in rep["letters"]["unprocessed"]:
        tickets.append(f"S4: письмо {l['ref']} без ack {l['age_h']}ч → {l['to'][:20]}")
    if a.json:
        print(json.dumps({**rep, "tickets": tickets}, ensure_ascii=False, indent=1))
    else:
        print(f"== lineage-audit ({REPO}) ==")
        s = rep["sessions"]
        if s:
            print(f"сессии: {s['total']}, сирот: {s['orphan']}, рёбра: {s['edges']}")
        b = rep["branches"]
        print(f"ветки task/*: {b['total']}, owner: {b['with_owner']}, "
              f"сирот: {len(b['orphan'])}, stale: {len(b['stale'])}")
        print(f"worktrees: {rep['worktrees']['count']}, letters: "
              f"{rep['letters']['refs']} refs, без ack: {len(rep['letters']['unprocessed'])}")
        print("-- тикеты --" if tickets else "ЧИСТО")
        for t in tickets:
            print(" •", t)
    return 1 if tickets else 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    pa = sub.add_parser("append", help="запись-факт/ревизия в ledger (flock)")
    for k in ("kind", "session-id", "branch", "worktree", "task", "pr",
              "status", "stage", "via", "ref", "edge", "repo", "note"):
        pa.add_argument(f"--{k}", dest=k.replace("-", "_"))
    pa.set_defaults(fn=cmd_append)
    pu = sub.add_parser("audit", help="read-only сшивка источников")
    pu.add_argument("--json", action="store_true")
    pu.set_defaults(fn=cmd_audit)
    pst = sub.add_parser("status", help="последняя ревизия session_id (revise_status-читатель)")
    pst.add_argument("--session-id", required=True)
    pst.set_defaults(fn=cmd_status)
    a = p.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
