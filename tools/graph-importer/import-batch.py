#!/usr/bin/env python3
"""import-batch — перенос карточек-кандидатов Лабы в граф волта (Task 5,
Р-036: holes→0 бинарная цель; карточка вне реестра = дыра остаётся дырой).

Читает пакет docs/specs/lab-graph-cards-batchN.jsonl (kind=finding,
status=candidate, provenance: session-id + msgs + hole_class) и добавляет в
04-Memory/idea-graph:
  - узел (nodes.jsonl): id n-XXXX (новый по счётчику), kind=finding,
    status=candidate, label — из карточки («без заголовка: sid» допустим);
  - ребро (edges.jsonl): from=session-id → to=new node, type=session-work,
    status=candidate;
дедупликация: на сессию — одно ребро (повторный импорт той же сессии не
плодит узлы). Append-only; --dry без записи.

Запуск: python3 import-batch.py --batch <путь к jsonl> [--dry]
"""
import argparse
import json
import os
import re
import time

DG = os.path.expanduser("~/Projects/OpenCode-Vault/04-Memory/idea-graph")
NODES = os.path.join(DG, "nodes.jsonl")
EDGES = os.path.join(DG, "edges.jsonl")


def _scan_int(path, prefix, field="id"):
    mx = 0
    if not os.path.exists(path):
        return 0
    for line in open(path, encoding="utf-8"):
        try:
            i = json.loads(line).get(field, "")
            m = re.fullmatch(prefix + r"(\d+)", str(i))
            if m:
                mx = max(mx, int(m.group(1)))
        except Exception:  # noqa: BLE001
            continue
    return mx


def _load(path):
    out = []
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    return out


def main():
    ap = argparse.ArgumentParser(prog="import-batch")
    ap.add_argument("--batch", required=True)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    cards = _load(args.batch)
    edges = _load(EDGES)
    # дедуп: какие session-id уже имеют ребро в графе
    linked = {str(e.get("from")) for e in edges if e.get("from")}

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    n_next = _scan_int(NODES, r"n-") + 1
    e_next = _scan_int(EDGES, r"e-") + 1
    new_nodes, new_edges, skipped = [], [], []
    for c in cards:
        prov = c.get("provenance") or {}
        sid = str(prov.get("session_id")
                  or prov.get("source", "").replace("session:", ""))
        if not sid:
            skipped.append((c.get("id"), "no-session"))
            continue
        if sid in linked:
            skipped.append((c.get("id"), "already-linked"))
            continue
        label = c.get("label") or f"без заголовка: {sid}"
        nid = f"n-{n_next:04d}"
        n_next += 1
        new_nodes.append({
            "id": nid, "graph": "stream",
            "kind": "finding", "status": "candidate",
            "label": label,
            "provenance": {"source": f"lab-graph-cards:{c.get('id', '?')}",
                           "observed_at": now, "session_id": sid,
                           "msgs": prov.get("msgs"),
                           "hole_class": prov.get("hole_class", "uncovered")},
            "projection": ["graph"],
        })
        new_edges.append({
            "id": f"e-{e_next:04d}", "graph": "stream",
            "from": sid, "to": nid,
            "type": "session-work", "status": "candidate",
            "provenance": {"source": f"lab-graph-cards:{c.get('id', '?')}",
                           "observed_at": now, "session_id": sid},
            "projection": ["graph"],
        })
        e_next += 1
        linked.add(sid)

    if args.dry:
        print(f"IMPORT-DRY nodes={len(new_nodes)} edges={len(new_edges)} "
              f"skipped={len(skipped)}")
        return 0
    if new_nodes:
        with open(NODES, "a", encoding="utf-8") as f:
            for n in new_nodes:
                f.write(json.dumps(n, ensure_ascii=False) + "\n")
    if new_edges:
        with open(EDGES, "a", encoding="utf-8") as f:
            for e in new_edges:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"IMPORT nodes={len(new_nodes)} edges={len(new_edges)} "
          f"skipped={len(skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
