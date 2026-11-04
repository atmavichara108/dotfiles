#!/usr/bin/env python3
"""id-collisions — read-only проверка пересечений ID по поверхностям (связка-0).

Запрос ЦСПМ (2026-11-04): автопроверка коллизий ID в карте ID. Скрипт только
читает источники и пишет свою проекцию в logs/linkage/. Чужие реестры не
правит (Р-056).

Что проверяет:
  - дубли ID внутри одной поверхности (коллизия);
  - один и тот же ID на разных поверхностях (пересечение — сигнал связки).

Поверхности: TASKS (T-), quests (Q-), tech-debt (TD-), decisions (Р-/Р-Д-),
waits (id + ref), goals sidecar (sessionID).

Использование:
  id-collisions.py build [--dry-run]
  id-collisions.py show
"""
import argparse
import glob
import json
import os
import re
import subprocess
import time

HOME = os.path.expanduser("~")
VAULT = os.path.join(HOME, "Projects/OpenCode-Vault")
DOT = os.path.join(HOME, "dotfiles")
WAITS = os.path.join(HOME, ".local/share/ship-mail/waits.jsonl")
GOALS = os.path.join(HOME, ".local/state/opencode/goals")
OUT_DIR = os.path.join(DOT, "logs/linkage")
OUT_JSON = os.path.join(OUT_DIR, "id-collisions.json")
OUT_MD = os.path.join(OUT_DIR, "id-collisions.md")

RE_T = re.compile(r"\bT-\d+\b")
RE_Q = re.compile(r"\bQ-\d+(?:\.\d+)?\b")
RE_TD = re.compile(r"\bTD-\d+\b")
RE_R = re.compile(r"\bР-(?:Д-)?\d+\b")
IGNORE_IDS = {"T-000"}  # исторический placeholder-бакет, не коллизия


def _read_lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.readlines()
    except OSError:
        return []


def _table_ids(path, id_re):
    """ID из первой ячейки markdown-таблицы."""
    out = []
    for n, line in enumerate(_read_lines(path), 1):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and id_re.fullmatch(cells[0]):
            out.append((cells[0], f"{path}:{n}"))
    return out


def _decision_ids(path):
    out = []
    for n, line in enumerate(_read_lines(path), 1):
        if not line.startswith("- **Р-"):
            continue
        m = RE_R.search(line)
        if m:
            out.append((m.group(0), f"{path}:{n}"))
    return out


def _waits_ids():
    out = []
    if not os.path.exists(WAITS):
        return out
    for n, line in enumerate(_read_lines(WAITS), 1):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("id"):
            out.append((f"wait:{d['id']}", f"{WAITS}:{n}"))
        ref = str(d.get("ref") or "")
        for m in re.finditer(r"\b(?:T-\d+|Q-\d+(?:\.\d+)?|TD-\d+)\b", ref):
            out.append((m.group(0), f"{WAITS}:{n}:ref"))
    return out


def _goal_ids():
    out = []
    if not os.path.isdir(GOALS):
        return out
    for path in sorted(glob.glob(os.path.join(GOALS, "*.json"))):
        name = os.path.basename(path)[:-5]
        out.append((f"goal:{name}", path))
    return out


def collect():
    sources = {
        "tasks": _table_ids(os.path.join(VAULT, "TASKS.md"), RE_T),
        "quests": _table_ids(os.path.join(VAULT, "11-Quests/quests.md"), RE_Q),
        "techdebt": _table_ids(os.path.join(VAULT, "04-Memory/tech-debt-2026-10-23.md"), RE_TD),
        "decisions": _decision_ids(os.path.join(VAULT, "01-Policies/decisions-registry.md")),
        "waits": _waits_ids(),
        "goals": _goal_ids(),
    }
    return sources


def build(dry_run=False):
    sources = collect()
    by_id = {}
    for surface, pairs in sources.items():
        for ident, loc in pairs:
            if ident in IGNORE_IDS:
                continue
            by_id.setdefault(ident, {}).setdefault(surface, []).append(loc)

    within = {}
    cross = {}
    for ident, surfaces in by_id.items():
        for surface, locs in surfaces.items():
            if len(locs) > 1:
                within.setdefault(surface, []).append({"id": ident, "hits": locs})
        if len(surfaces) > 1:
            cross[ident] = {s: v for s, v in surfaces.items()}

    result = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "surfaces": {k: len(v) for k, v in sources.items()},
        "within_surface_duplicates": within,
        "cross_surface_intersections": cross,
        "rc": 2 if (within or cross) else 0,
    }
    if dry_run:
        print(f"ID-COLLISIONS dry-run surfaces={result['surfaces']} "
              f"within={sum(len(v) for v in within.values())} cross={len(cross)} rc={result['rc']}")
        for s, items in within.items():
            for it in items[:10]:
                print(f"- within {s}: {it['id']} x{len(it['hits'])}")
        for ident, surfaces in list(cross.items())[:20]:
            print(f"- cross {ident}: {', '.join(surfaces)}")
        return result["rc"]

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
        f.write("\n")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("# ID-коллизии и пересечения (read-only)\n\n")
        f.write(f"собрано: {result['ts']}\n\n")
        f.write("## Поверхности\n\n")
        for k, v in result["surfaces"].items():
            f.write(f"- {k}: {v}\n")
        f.write(f"\n## Дубли внутри поверхности ({sum(len(v) for v in within.values())})\n\n")
        for s, items in within.items():
            for it in items:
                f.write(f"- {s}: {it['id']} x{len(it['hits'])} — {', '.join(it['hits'][:3])}\n")
        f.write(f"\n## Пересечения между поверхностями ({len(cross)})\n\n")
        for ident, surfaces in cross.items():
            f.write(f"- {ident}: {', '.join(surfaces)}\n")
    print(f"ID-COLLISIONS surfaces={result['surfaces']} "
          f"within={sum(len(v) for v in within.values())} cross={len(cross)} rc={result['rc']}")
    print(f"-> {OUT_JSON}")
    print(f"-> {OUT_MD}")
    return result["rc"]


def show():
    if not os.path.exists(OUT_MD):
        print("нет сборки — запусти: id-collisions.py build")
        return 1
    print(open(OUT_MD, encoding="utf-8").read())
    return 0


def main():
    ap = argparse.ArgumentParser(description="ID-коллизии по поверхностям (read-only)")
    ap.add_argument("cmd", nargs="?", default="build", choices=["build", "show"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.cmd == "show":
        return show()
    return build(dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
