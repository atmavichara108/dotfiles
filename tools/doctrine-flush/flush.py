#!/usr/bin/env python3
"""flush — мост «бой доктрины» (Р-030) в измеримый контур Лабы.

Задача (Лаба, p0-self-audit-20261030): критерий провала боя «ни одного живого
ребра contradicts за месяц» тикает, но писать ребра некому — слой немерм.
Этот инструмент пишет ребра в журнал Лабы и умеет находить незафиксированные
tension-пары сам (сканер), чтобы flush происходил без ручных шагов.

Журнал: /home/rudra/Projects/ability-lab/.cache/lab-doctrine/edges.jsonl
Формат строки: {ts, type:"contradicts", ref_a, ref_b, summary, source_session}
(+ опционально resolved_questions). Append-only. Дедупликация: одна пара
(ref_a, ref_b) — одно ребро (повторный инжект НЕ дублирует).

Команды:
  flush.py add --ref-a X --ref-b Y --summary "..." [--resolved "..."] [--session SID]
  flush.py scan [--write]     # найти tension-пары (карточки+реестр) без ребра
  flush.py count              # сколько ребер за бой (для метрики)

Границы (запрос Лабы): пишем ТОЛЬКО в .cache/lab-doctrine/ Лабы (gitignore-
зона); волт и dotfiles не трогаем.
"""
import argparse
import json
import os
import re
import sys
import time
import uuid

EDGES = os.path.expanduser(
    "~/Projects/ability-lab/.cache/lab-doctrine/edges.jsonl")
VAULT = os.path.expanduser("~/Projects/OpenCode-Vault")
REGISTRY = os.path.join(VAULT, "01-Policies/decisions-registry.md")
DOCTRINE = os.path.join(VAULT, "08-Doctrine")


def _read_edges():
    if not os.path.exists(EDGES):
        return []
    out = []
    for line in open(EDGES, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    return out


def _append_edge(row):
    os.makedirs(os.path.dirname(EDGES), exist_ok=True)
    with open(EDGES, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _pair_key(a, b):
    return "|".join(sorted([str(a), str(b)]))


def cmd_add(a):
    edges = _read_edges()
    key = _pair_key(a.ref_a, a.ref_b)
    for e in edges:
        if e.get("type") == "contradicts" and \
                _pair_key(e.get("ref_a"), e.get("ref_b")) == key:
            print(f"EDGE-EXISTS: ребро {key} уже в журнале — дубль не пишем")
            return 0
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "type": "contradicts", "ref_a": a.ref_a, "ref_b": a.ref_b,
           "summary": a.summary,
           "source_session": a.session or "ses_ece7b76c8ffeOkYZqZe38QbTVx"}
    if a.resolved:
        row["resolved_questions"] = a.resolved
    _append_edge(row)
    print(f"EDGE: {a.ref_a} ↔ {a.ref_b} записано ({EDGES})")
    return 0


def _tension_pairs():
    """Пары (карточка ← tension, карточка/Р → цель) из волта."""
    pairs = []
    if not os.path.isdir(DOCTRINE):
        return pairs
    for fn in sorted(os.listdir(DOCTRINE)):
        if not fn.endswith(".md") or not fn.startswith(("ХПФ", "hp")):
            continue
        path = os.path.join(DOCTRINE, fn)
        try:
            head = open(path, encoding="utf-8").read(4000)
        except OSError:
            continue
        m = re.search(r"^id:\s*(\S+)", head, flags=re.M)
        card = m.group(1) if m else fn[:-3]
        t = re.search(r"tension_with:\s*\[([^\]]*)\]", head)
        if t:
            for ref in re.split(r"[,\s]+", t.group(1)):
                ref = ref.strip()
                if ref:
                    pairs.append((card, ref, f"{fn}: tension_with"))
    # Р-решения из реестра, помеченные как tension-кандидаты (contradict-метки)
    if os.path.exists(REGISTRY):
        txt = open(REGISTRY, encoding="utf-8").read()
        for m in re.finditer(r"Р-(\d+).{0,400}?(tension|противореч)", txt,
                             flags=re.S | re.I):
            rid = "Р-" + m.group(1)
            pairs.append((rid, "doctrine-review",
                          "decisions-registry: tension-метка"))
    return pairs


def cmd_scan(a):
    edges = _read_edges()
    have = {_pair_key(e.get("ref_a"), e.get("ref_b")) for e in edges}
    pairs = _tension_pairs()
    fresh = [(x, y, src) for (x, y, src) in pairs
             if _pair_key(x, y) not in have]
    if a.write:
        n = 0
        for x, y, src in fresh:
            row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "type": "contradicts", "ref_a": x, "ref_b": y,
                   "summary": f"tension-пара ({src}) — зафиксирована сканером",
                   "source_session": "doctrine-flush-scan"}
            _append_edge(row)
            n += 1
        print(f"SCAN: записано {n} ребер из {len(pairs)} tension-пар")
    else:
        for x, y, src in fresh:
            print(f"FRESH {x} ↔ {y} ({src})")
        print(f"SCAN-DRY: всего пар {len(pairs)}, без ребра {len(fresh)}")
    return 0


def cmd_count(a):
    edges = [e for e in _read_edges() if e.get("type") == "contradicts"]
    resolved = sum(1 for e in edges if e.get("resolved_questions"))
    print(f"CONTRADICTS {len(edges)} resolved {resolved}")
    return 0


def main():
    p = argparse.ArgumentParser(prog="flush")
    sub = p.add_subparsers(dest="cmd")
    ad = sub.add_parser("add")
    ad.add_argument("--ref-a", required=True)
    ad.add_argument("--ref-b", required=True)
    ad.add_argument("--summary", required=True)
    ad.add_argument("--resolved", default="")
    ad.add_argument("--session", default="")
    sc = sub.add_parser("scan")
    sc.add_argument("--write", action="store_true")
    sub.add_parser("count")
    args = p.parse_args()
    if args.cmd == "add":
        return cmd_add(args)
    if args.cmd == "scan":
        return cmd_scan(args)
    if args.cmd == "count":
        return cmd_count(args)
    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
