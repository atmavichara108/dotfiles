#!/usr/bin/env python3
"""rudrakshas — цифровой образ Рудры, ступень А1 «справка» (Р-012, Р-018).

Read-only. Периметр: только решения владельца (basis: quoted) из реестров.
Каждая цитата: файл:строка + git SHA + 100% дословность (verbatim, без пересказа).
Каждый вывод помечен: «это модель, не Rudra».
Без нового runtime (python3, никаких серверов). Запрет: не используется
в цепочках исполнения — только чтение.

Производные (индекс слов, реестр паттернов) — в dotfiles рядом с
user-profile.md (слово владельца через ЦУ 2026-10-20).
Пересборка — по коммиту (дата среза = SHA исходника).

Лестница: А4 (переноси контур, не текст) → А1 (справка) → А2 → А3.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
SOURCES = [
    # (репо, путь, ветка main которой верим)
    (HOME / "dotfiles", ".opencode/memory/decisions.md"),
    (HOME / "dotfiles", "docs/decisions.md"),
    (HOME / "Projects/OpenCode-Vault", "01-Policies/decisions-registry.md"),
    (HOME / "Projects/OpenCode-Vault", "01-Policies/organ-structure-2026-10-18.md"),
    (HOME / "Projects/OpenCode-Vault", "99-Inbox/2026-10-14-temple-resolutions.md"),
]
MARKER = "\n⚠️ Это модель, не Rudra. Каждая цитата дословна; источник: {ref}"
QUOTE_RE = re.compile(r"[«\"]([^»\"]{10,})[»\"]")


def git_sha(repo: Path) -> str:
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "?"


def quotes_from_line(line: str) -> list[str]:
    return [m for m in QUOTE_RE.findall(line)]


def load_corpus() -> list[dict]:
    """Корпус = строки с кавычками (basis: quoted — решения владельца)."""
    corpus: list[dict] = []
    for repo, rel in SOURCES:
        path = repo / rel
        if not path.exists():
            continue
        sha = git_sha(repo)
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for q in quotes_from_line(line):
                corpus.append({
                    "text": q, "repo": str(repo), "file": rel, "line": i, "sha": sha
                })
    return corpus


def search(query: str, corpus: list[dict], limit: int = 10) -> list[dict]:
    """Честный поиск: полное совпадение слова → подстрока. Никакой генерации."""
    ql = query.lower()
    exact = [c for c in corpus if ql in c["text"].lower()]
    return exact[:limit]


def spravka(query: str) -> str:
    corpus = load_corpus()
    hits = search(query, corpus)
    if not hits:
        return "Не найдено дословных решений по запросу." + MARKER.format(
            ref=f"корпус {len(corpus)} цитат")
    out = []
    for h in hits:
        out.append(f"«{h['text']}»\n  {h['file']}:{h['line']} (SHA {h['sha']})")
    return "\n\n".join(out) + MARKER.format(
        ref=f"{len(hits)} из {len(corpus)} цитат")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    print(spravka(" ".join(sys.argv[1:])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
