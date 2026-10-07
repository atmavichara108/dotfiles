#!/usr/bin/env python3
"""Git Freed — детектор владения деревом (kernel-позиция: dotfiles, контур B10).

Перенос канонического детектора из волта (tools/git-agent/freed.py, паттерн-
режим acc6023) с адаптацией под dotfiles-пути и формат реестра peer-comms.

Детерминированный read-only скан: ветка/main-щит, грязное дерево по путям,
активные leases и сессии (tools/peer-comms/claims.jsonl), маркеры конфликтов,
предупреждение о гонке параллельных писателей общего поля.

LLM внутри нет — «данные, а не решения»; выводы делает агент (git-freed).

Классификация грязи (различение routine/common-field/lease/guest):
    routine      — tracked-правки остальной зоны (свой scope, рутина)
    common-field — любые *.jsonl в общей зоне (см. is_common_field)
    guest        — untracked-файлы (потенциально чужие/новые)
    lease        — активные сессии по реестру peer-comms (отдельный ключ)

Общая зона (паттерн-режим, контракт git-freed.md S5/S8.1):
    любой *.jsonl рекурсивно внутри COMMON_DIR, кроме archive/_archive.
    В dotfiles такой зоны сейчас нет — детектор молчит на прод-дереве
    (ноль ложных срабатываний), а срабатывает на реальной гонке.

Команды:
    freed.py detect      # полный снапшот: JSON в stdout (ключи стабильны)
    freed.py check       # гейт перед commit: 0 ok | 1 warn | 2 blocked
    freed.py lease-list  # активные сессии/leases с TTL (текстом)
Exit-семантика check:
    0 — поддержка чистая, гейт пройден
    1 — предупреждения: общее поле dirty, дубль id, чужие leases, churn
    2 — блокировка: merge/unmerged-путь/конфликт-маркер, main/master
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLAIMS = REPO / "tools" / "peer-comms" / "claims.jsonl"
COMMON_DIR = "04-Memory/idea-graph"
# Общие append-only поля распознаются ШАБЛОНОМ: любой *.jsonl рекурсивно
# в общей зоне (включая подкаталоги/песочницы). Архив — не живое поле.
COMMON_EXCLUDE_DIRS = ("_archive", "archive")
DEFAULT_TTL_MIN = 30


def run(args: list[str]) -> str:
    try:
        return subprocess.run(
            args, cwd=str(REPO), capture_output=True, text=True, check=False
        ).stdout.strip()
    except FileNotFoundError:
        return ""


def is_conflict() -> tuple[bool, str]:
    git = REPO / ".git"
    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"):
        if (git / marker).exists():
            return True, marker
    if "unmerged" in run(["git", "status", "--porcelain=v1"]):
        return True, "unmerged-path"
    return False, ""


def dirty_map() -> dict[str, str]:
    out = run(["git", "status", "--porcelain=v1", "--untracked-files=all"])
    res: dict[str, str] = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        code, path = line[:2], line[2:].strip().strip('"')
        res[path] = code
    return res


def active_claims() -> list[dict]:
    """Fold claims.jsonl (формат dotfiles peer-comms: hello/ack/bye).

    Сессия активна если последняя запись — hello/ack (не bye) и возраст
    в пределах TTL (поле ttl_minutes записи, иначе DEFAULT_TTL_MIN).
    """
    last: dict[str, dict] = {}
    if not CLAIMS.exists():
        return []
    for line in CLAIMS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        session = rec.get("session")
        if isinstance(session, str) and session:
            last[session] = rec
    now = int(time.time())
    live = []
    for session, rec in last.items():
        if rec.get("op") == "bye":
            continue
        ts = rec.get("ts") or rec.get("time") or 0
        age = max(0, now - int(ts)) if ts else 0
        ttl_min = rec.get("ttl_minutes") or DEFAULT_TTL_MIN
        fresh = age <= int(ttl_min) * 60
        live.append(
            {
                "claim_id": session,
                "holder": session,
                "role": rec.get("role", "?"),
                "scope": rec.get("scope", "?"),
                "model": rec.get("model", ""),
                "age_sec": age,
                "fresh": fresh,
            }
        )
    return live


def is_common_field(path: str) -> bool:
    """Общее append-поле = любой *.jsonl рекурсивно под COMMON_DIR
    (включая подкаталоги/песочницы). Архивы — не живое поле."""
    if not path.startswith(COMMON_DIR + "/"):
        return False
    if not path.endswith(".jsonl"):
        return False
    rel = path[len(COMMON_DIR) + 1:]
    return not any(seg in COMMON_EXCLUDE_DIRS for seg in rel.split("/")[:-1])


def classify(dirty: dict[str, str]) -> dict:
    common_dirty = [p for p in dirty if is_common_field(p)]
    trash = [p for p, c in dirty.items() if c in {"??", "A ", "AM"} and
             (p.startswith("/tmp") or p == ".DS_Store")]
    routine = [p for p, c in dirty.items()
               if c != "?" + "?" and not is_common_field(p) and p not in trash]
    guest = [p for p, c in dirty.items()
             if c == "??" and not is_common_field(p) and p not in trash]
    return {
        "common_field_dirty": common_dirty,
        "routine_tracked": routine,
        "guest_untracked": guest,
        "junk_candidates": trash,
    }


def common_health() -> list[str]:
    """Проверить JSONL-поля общей зоны на битые строки и дублирующиеся id."""
    warnings: list[str] = []
    root = REPO / COMMON_DIR
    if not root.exists():
        return warnings
    for path in sorted(root.rglob("*.jsonl")):
        rel = path.relative_to(REPO).as_posix()
        if not is_common_field(rel):
            continue
        seen: set[object] = set()
        duplicate_ids: set[object] = set()
        try:
            with path.open(encoding="utf-8") as stream:
                for line_no, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        warnings.append(f"bad-json:{rel}:{line_no}")
                        continue
                    if not isinstance(record, dict) or "id" not in record:
                        continue
                    record_id = record["id"]
                    try:
                        duplicate = record_id in seen
                        seen.add(record_id)
                    except TypeError:
                        continue
                    if duplicate and record_id not in duplicate_ids:
                        warnings.append(f"dup-id:{rel}:{record_id}")
                        duplicate_ids.add(record_id)
        except (OSError, UnicodeError):
            continue
    return warnings


def detect() -> dict:
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"]) or "?"
    head = run(["git", "rev-parse", "HEAD"])[:12]
    dirty = dirty_map()
    conf, marker = is_conflict()
    claims = active_claims()
    cls = classify(dirty)
    health = common_health()
    warnings: list[str] = []
    blocked: list[str] = []
    if conf:
        blocked.append(f"merge-state:{marker}")
    if branch in ("main", "master"):
        blocked.append("branch:main-denied")
    if cls["common_field_dirty"]:
        warnings.append("common-field:" + ",".join(cls["common_field_dirty"]))
    warnings.extend(health)
    live = [c for c in claims if c["fresh"]]
    if live:
        warnings.append("leases:" + ",".join(c["claim_id"] for c in live))
    if len(dirty) > 40:
        warnings.append(f"tree-churn:{len(dirty)}")
    return {
        "ts": round(time.time() * 1000),
        "repo": REPO.name,
        "branch": branch,
        "head": head,
        "dirty_count": len(dirty),
        "classify": cls,
        "claims": claims,
        "common_health": health,
        "warnings": warnings,
        "blocked": blocked,
        "ok": not blocked,
    }


def cmd_detect() -> int:
    print(json.dumps(detect(), ensure_ascii=False, indent=2))
    return 0


def cmd_check() -> int:
    d = detect()
    if d["blocked"]:
        print("BLOCKED: " + "; ".join(d["blocked"]))
        return 2
    if d["warnings"]:
        print("WARN: " + "; ".join(d["warnings"]))
        return 1
    print(f"OK: no blocks (dirty_count={d['dirty_count']}, branch={d['branch']})")
    return 0


def cmd_lease_list() -> int:
    live = [c for c in active_claims() if c["fresh"]]
    if not live:
        print("no active leases")
        return 0
    for c in live:
        print(f"{c['claim_id']}  role={c['role']}  scope={c['scope']}")
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "detect"
    if cmd == "detect":
        return cmd_detect()
    if cmd == "check":
        return cmd_check()
    if cmd == "lease-list":
        return cmd_lease_list()
    print(f"unknown command: {cmd} (detect|check|lease-list)", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main())
