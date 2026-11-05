#!/usr/bin/env python3
"""metka2 — жизненный цикл и приёмка живых меток (дополнение ЦУ 2026-11-06).

Реестр: logs/follower/metka2.jsonl (append-only).
Источники: waits.jsonl, waits-done.jsonl, produced-annotations.jsonl,
peer-registry.md. Источники не правятся; append-only пишет только metka2.

Правила (кратко):
  - node обязателен: sid без лица -> метка не принимается (L5);
  - одна активная метка на строку (L1 деактивация, stale-parent);
  - ответ/пришивка -> state=answered (L2);
  - форм-/портальный вопрос -> state=asked (L3);
  - нет строки/адресата -> no-meta (L4);
  - экран пересчитывает derived из источника (A6): расхождение -> stale-meta
    с именем источника + append-only обновление метки.

Команды:
  metka2.py apply   # привести активные метки к пересчёту и починить дубли
  metka2.py check   # приёмка A1-A6, rc 0 pass / 2 defect
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

HOME = Path.home()
DOT = HOME / "dotfiles"
WAITS = HOME / ".local/share/ship-mail/waits.jsonl"
DONE = HOME / ".local/share/ship-mail/waits-done.jsonl"
ANN = DOT / "logs/follower/produced-annotations.jsonl"
METKA2 = DOT / "logs/follower/metka2.jsonl"
PEER = HOME / "Projects/OpenCode-Vault/04-Memory/peer-registry.md"

SID_RE = re.compile(r"^ses_[A-Za-z0-9]{12,}$")


def _rows(path):
    if not os.path.exists(path):
        return []
    out = []
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        d["_line"] = n
        out.append(d)
    return out


def _append(entry):
    os.makedirs(METKA2.parent, exist_ok=True)
    with open(METKA2, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _peer_nodes():
    nodes = {}
    if not PEER.exists():
        return nodes
    for line in open(PEER, encoding="utf-8"):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        m = re.search(r"\b(ses_[A-Za-z0-9]+)\b", cells[1])
        if m and cells[0]:
            nodes[m.group(1)] = re.sub(r"\*\*|\[\[|\]\]", "", cells[0])
    return nodes


def _load_waits():
    active, closed = {}, {}
    for d in _rows(WAITS):
        if d.get("id"):
            active[d["id"]] = d
    for d in _rows(DONE):
        if d.get("op") == "stitch" and d.get("reply_to"):
            closed[d["reply_to"]] = d
        if d.get("id"):
            closed[d["id"]] = d
    return active, closed


def _annotation_latest():
    out = {}
    for d in _rows(ANN):
        if d.get("id"):
            out[d["id"]] = d
    return out


def _node_for(ann, peer_nodes, active=None, closed=None):
    # приоритет: источник waits (кто должен), потом produced-метка
    wid = str(ann.get("id"))
    w = (active or {}).get(wid) or (closed or {}).get(wid)
    addressee = str((w or {}).get("who_owes") or ann.get("addressee") or "")
    if not addressee or addressee in ("БЕЗ МЕТКИ", "неоднозначен"):
        return "", ""
    if addressee == "owner":
        return "Владелец", "owner"
    if SID_RE.match(addressee):
        return peer_nodes.get(addressee, ""), "session"
    return addressee, "text"


def _ticket(ann):
    return str(ann.get("ticket") or "")


def _expected_state(ann, active, closed):
    wid = str(ann.get("id"))
    if wid in closed:
        c = closed[wid]
        if (c.get("op") == "stitch" or c.get("answered_by")
                or c.get("state") == "answered"):
            return "answered", "waits-done/stitch"
        return "closed-no-answer", "waits-done/closed-no-answer"
    if wid in active:
        return "asked", "source:waits:open"
    return "no-meta", "source:absent"


def _metka2_active(rows):
    deactivated = {r.get("parent") for r in rows if r.get("op") == "deactivate"}
    active = {}
    for r in rows:
        if r.get("op") == "deactivate":
            continue
        if not r.get("id") or r.get("active") is False:
            continue
        if r.get("metka2_id") in deactivated:
            continue
        active[r["id"]] = r
    return active


def _apply():
    peer_nodes = _peer_nodes()
    active_waits, closed_waits = _load_waits()
    anns = _annotation_latest()
    metka2_rows = _rows(METKA2)
    active_metka2 = _metka2_active(metka2_rows)
    created = []
    deactivated = []

    # Дедуп produced-annotations: все предыдущие маркеры одной строки, кроме
    # последнего, становятся stale-parent в metka2 (не удаляем источник).
    by_id = {}
    for d in _rows(ANN):
        by_id.setdefault(d.get("id"), []).append(d)
    for wid, rows in by_id.items():
        if len(rows) > 1:
            keep = rows[-1]
            for old in rows[:-1]:
                marker = f"produced-annotations.jsonl#{old['_line']}"
                _append({"op": "deactivate", "id": wid, "parent": marker,
                         "reason": "duplicate-produced-meta: keep "
                                   f"produced-annotations.jsonl#{keep['_line']}",
                         "ts": _now(), "meta_by": "follower-rule"})
                deactivated.append(marker)

    for wid, ann in anns.items():
        node, cls = _node_for(ann, peer_nodes, active_waits, closed_waits)
        state, source = _expected_state(ann, active_waits, closed_waits)
        # если нет лица — метка v2 не принимается; помечаем в журнале как no-meta
        if not node:
            state = "no-meta"
            source = "L5: addressee without node"
        old = active_metka2.get(wid)
        new_state = state
        if old and old.get("state") == new_state and old.get("node") == node:
            continue
        parent = old.get("metka2_id") if old else None
        mid = _metka2_id()
        record = {"op": "metka2", "metka2_id": mid, "id": wid,
                  "parent": parent, "active": True,
                  "node": {"name": node, "class": cls},
                  "state": new_state, "since": ann.get("since") or _now(),
                  "changed_at": _now(),
                  "change_reason": source,
                  "ready_proxy": new_state == "ready",
                  "meta_by": "follower-rule",
                  "source": f"follower-recompute:{source}"}
        _append(record)
        created.append(record)
        if old:
            _append({"op": "deactivate", "id": wid, "parent": parent,
                     "reason": "superseded-by-newer-metka",
                     "ts": _now(), "meta_by": "follower-rule"})
            deactivated.append(parent)
    print(f"METKA2 APPLY created={len(created)} deactivated={len(deactivated)} "
          f"file={METKA2}")
    return 0


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _metka2_id():
    base = int(time.time() * 1000) % (16 ** 8)
    existing = {r.get("metka2_id") for r in _rows(METKA2)}
    for n in range(4096):
        mid = "%08x" % ((base + n) % (16 ** 8))
        if mid not in existing:
            return mid
    raise SystemExit("metka2: нет свободного id")


def _check():
    peer_nodes = _peer_nodes()
    active_waits, closed_waits = _load_waits()
    anns = _annotation_latest()
    metka2_rows = _rows(METKA2)
    active = _metka2_active(metka2_rows)
    defects = []
    counts = {}
    for wid, ann in anns.items():
        mark = active.get(wid)
        node, cls = _node_for(ann, peer_nodes, active_waits, closed_waits)
        state, source = _expected_state(ann, active_waits, closed_waits)
        effective_node = (mark.get("node", {}).get("name")
                          if mark else node)
        effective_state = (mark.get("state") if mark else "no-meta")
        if wid in _duplicates(metka2_rows):
            defects.append(f"A2 {wid}: две активные metka2")
        if effective_state == "no-meta":
            # отсутствие метки — честный датчик, не дефект A1
            counts.setdefault("no-meta", []).append(wid)
            continue
        if not effective_node:
            defects.append(f"A1 {wid}: адресат без лица")
        if effective_state != state:
            defects.append(f"A6 {wid}: метка {effective_state} ≠ источник "
                           f"{state} ({source})")
        if effective_state == "answered" and (
                mark or {}).get("ready_proxy") is True:
            defects.append(f"A3 {wid}: answered с готовностью")
        counts.setdefault(effective_state, []).append(wid)
    for wid in active_waits:
        mark = active.get(wid)
        node, _ = _node_for(anns.get(wid, {}), peer_nodes,
                            active_waits, closed_waits)
        if not mark or not node:
            defects.append(f"A1 {wid}: живая waits-строка без лица/metka")
    if defects:
        print("METKA2 CHECK FAIL")
        for d in defects:
            print("  - " + d)
        return 2
    print(f"METKA2 CHECK PASS counts={ {k: len(v) for k, v in counts.items() if isinstance(v, list)} }")
    return 0


def _duplicates(rows):
    deactivated = {r.get("parent") for r in rows if r.get("op") == "deactivate"}
    seen = {}
    for r in rows:
        if r.get("op") == "deactivate" or r.get("active") is False:
            continue
        if r.get("metka2_id") in deactivated:
            continue
        seen.setdefault(r["id"], []).append(r.get("metka2_id"))
    return {k: v for k, v in seen.items() if len(v) > 1}


def main():
    if len(sys.argv) < 2:
        print("usage: metka2.py apply|check")
        return 1
    return {"apply": _apply, "check": _check}.get(sys.argv[1], lambda: 1)()


if __name__ == "__main__":
    raise SystemExit(main())
