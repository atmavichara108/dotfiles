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
STALE_DAYS = 3
STALE_BEHIND = 10          # R3: stale = ≥10 коммитов позади origin/main ИЛИ ≥3 дней
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
    lines = [json.dumps(rec, ensure_ascii=False, separators=(",", ":"))]
    # R2: рождение с первичным статусом — fact + revision(live) одним flock-захватом
    if a.kind == "fact" and a.status and a.session_id:
        rec2 = {"ts": rec["ts"], "kind": "revision", "session_id": a.session_id,
                "status": a.status, "rev": 1, "via": a.via}
        lines.append(json.dumps(rec2, ensure_ascii=False, separators=(",", ":")))
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    fresh = not LEDGER.exists()
    with open(LEDGER, "a") as f:            # append-only, длина записи > pipe
        fcntl.flock(f, fcntl.LOCK_EX)       # буфера — только flock (ADR §5)
        for line in lines:
            f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())
    if fresh:
        os.chmod(LEDGER, 0o600)             # R1: права 600 на канонический ledger
    for line in lines:
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
    # R2(в): первый список аудита — сироты не отбрасываются (orphan:true), выводим список
    orphan_list = db_rows(
        "SELECT id, substr(coalesce(title,''),1,40), "
        "datetime(time_updated/1000,'unixepoch') FROM session_v2 "
        "WHERE parent_id IS NULL AND fork_session_id IS NULL "
        "ORDER BY time_updated DESC LIMIT 60")
    return {"total": total, "orphan": orphans, "edges": edges,
            "orphan_list": [{"id": r[0], "title": r[1], "updated": r[2]} for r in orphan_list]}


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
        behind = 0
        try:
            behind = int(sh(["git", "rev-list", "--count", f"origin/main..{name}"]).strip() or "0")
        except ValueError:
            behind = 0
        age_d = (now - int(ts)) / 86400
        if not in_main and (age_d >= STALE_DAYS or behind >= STALE_BEHIND):
            out["stale"].append({"branch": name, "age_d": round(age_d, 1), "behind": behind})
    return out


def audit_worktrees():
    wt = sh(["git", "worktree", "list"]).strip().splitlines()
    return {"count": len(wt), "paths": [l.split()[0] for l in wt][1:]}


def audit_letters():
    """Слой 3 (R5): sent → delivered → processed.
    sent: receipts-out.jsonl (event=sent);
    delivered: ledger edge=delivered-to (R2) или receipts delivered;
    processed: receipt started/finished с тем же ref ИЛИ ledger edge=ack (R5)."""
    now = time.time()
    by_ref: dict = {}
    n = 0
    ack_refs: set = set()
    delivered_refs: set = set()
    # --- ledger: ручные ack (R5) и рёбра доставки (R2) ---
    try:
        with open(LEDGER) as f:
            for l in f:
                try:
                    d = json.loads(l)
                except json.JSONDecodeError:
                    continue
                ref = d.get("ref")
                if not ref:
                    continue
                if d.get("edge") == "ack":
                    ack_refs.add(ref)
                elif d.get("edge") == "delivered-to" and ref:
                    delivered_refs.add(ref)
    except FileNotFoundError:
        pass
    # --- receipts: sent + ответы (started/finished) ---
    if not RECEIPTS_OUT.exists():
        return {"scanned": 0, "refs": 0, "unprocessed": [],
                "acked": len(ack_refs)}
    with open(RECEIPTS_OUT) as f:
        for l in f:
            try:
                d = json.loads(l)
            except json.JSONDecodeError:
                continue
            n += 1
            ref = d.get("ref") or d.get("scope") or "?"
            e = by_ref.setdefault(ref, {"sent_ts": now, "answered": False,
                                        "delivered": False,
                                        "to": d.get("to", "")})
            e["sent_ts"] = min(e["sent_ts"], d.get("ts", now))
            if str(d.get("receipt", "")) in ("started", "finished") and d.get("from"):
                e["answered"] = True
            if str(d.get("event", "")) in ("delivered", "timeout"):
                e["delivered"] = True
    for ref in by_ref:
        if ref in ack_refs:
            by_ref[ref]["answered"] = True
        if ref in delivered_refs:
            by_ref[ref]["delivered"] = True
    stale = [{"ref": r, "age_h": round((now - e["sent_ts"]) / 3600, 1), "to": e["to"]}
             for r, e in by_ref.items()
             if not e["answered"] and (now - e["sent_ts"]) / 3600 > UNPROCESSED_H]
    return {"scanned": n, "refs": len(by_ref), "unprocessed": stale,
            "acked": len(ack_refs)}


def cmd_ack(a):
    """R5: явная фиксация processed — «доставлено ≠ обработано».
    ack <ref> — письмо с этим ref обработано (вне канала ответа)."""
    if not a.ref:
        sys.exit("ack: нужен --ref")
    rec = {"ts": int(time.time()), "kind": "fact", "session_id": a.session_id,
           "edge": "ack", "ref": a.ref, "note": a.note or "manual ack"}
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    fresh = not LEDGER.exists()
    line = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
    with open(LEDGER, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())
    if fresh:
        os.chmod(LEDGER, 0o600)
    print(line)
    return 0


def snapshot_ledger():
    """R3: ротируемый снапшот ledger рядом (ledger.snapshot-<ts>.jsonl, keep 5)."""
    if not LEDGER.exists():
        return None
    import shutil
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = LEDGER.parent / f"ledger.snapshot-{stamp}.jsonl"
    shutil.copy2(LEDGER, dst)
    snaps = sorted(LEDGER.parent.glob("ledger.snapshot-*.jsonl"))
    for old in snaps[:-5]:
        old.unlink()
    return dst.name


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
    pck = sub.add_parser("ack", help="R5: ручная фиксация processed по ref (доставлено ≠ обработано)")
    pck.add_argument("--ref", required=True)
    pck.add_argument("--session-id")
    pck.add_argument("--note")
    pck.set_defaults(fn=cmd_ack)
    a = p.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
