#!/usr/bin/env python3
"""L9 — allowlist корпуса и хэш-снимок (шаг протокола 1).

Состав корпуса: lab-protocol-l9.md, «Материалы и ограничения», срез 2026-10-15.
Только пути и sha256; содержимое не печатается.
Выход: docs/specs/lab-l9-corpus-snapshot.txt (в репозиторий) и
vault/.cache/lab-l9/snapshot.json (у индекса).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

VAULT = Path("/home/rudra/Projects/OpenCode-Vault")

ALLOWLIST_DIRS = [
    VAULT / "04-Memory" / "session-log",
    VAULT / "99-Inbox",
]
ALLOWLIST_FILES = [
    VAULT / "04-Memory" / "facts.md",
    VAULT / "04-Memory" / "active-context.md",
    VAULT / "99-Inbox.md",
]
DENY_PATTERNS = (  # явные исключения (не входят)
    "04-Memory/idea-graph",
    "04-Memory/route-log",
    "04-Memory/index.md",
    "04-Memory/log.md",
)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def corpus_files() -> list[Path]:
    files: list[Path] = []
    for d in ALLOWLIST_DIRS:
        files.extend(sorted(p for p in d.rglob("*") if p.is_file() and p.suffix == ".md"))
    files.extend(p for p in ALLOWLIST_FILES if p.is_file())
    out = []
    for p in sorted(set(files)):
        rel = str(p.relative_to(VAULT))
        if any(pat in rel for pat in DENY_PATTERNS):
            continue
        out.append(p)
    return out


def main() -> int:
    files = corpus_files()
    snap = {str(p.relative_to(VAULT)): sha256(p) for p in files}
    out_repo = Path(__file__).resolve().parents[2] / "docs" / "specs" / "lab-l9-corpus-snapshot.txt"
    out_repo.write_text("".join(f"{h}  {n}\n" for n, h in sorted(snap.items())), encoding="utf-8")
    cache = VAULT / ".cache" / "lab-l9"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"файлов: {len(snap)}; снимок: {out_repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
