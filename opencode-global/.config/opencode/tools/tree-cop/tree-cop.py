#!/usr/bin/env python3
"""tree-cop — коп чистоты дерева для параллельных агентных сессий.

Максимум кода, минимум модели: классификация грязи, именованный stash
чужого, гейты для /ship. Агент только вызывает и читает вердикт.

Использование:
  tree-cop.py status --mine <path>...     JSON: ветка, своя/чуждая грязь, вердикт
  tree-cop.py stash-foreign --mine ... -m "msg"   stash ТОЛЬКО чужого (pathspec)
  tree-cop.py pop                              вернуть последний stash копа
  tree-cop.py ship-check --mine ...           гейты шага 0 /ship (exit 0 = GO)

Правила атрибуции:
  - tracked-изменение: своё iff путь в --mine, иначе чужое;
  - untracked: своё iff путь под одним из --mine префиксов/файлов, иначе чужое;
  - skip-worktree биты (S) и mode-правки показываются отдельно — это
    невидимая грязь, из-за которой чаще всего всё и ломается.

Контракт вывода: одна строка JSON {"ok": true, ...} | {"ok": false, ...}.
Exit: 0 GO/успех · 1 STOP/ошибка.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_git(*args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, f"git недоступен: {exc}"
    return proc.returncode, (proc.stdout or "").strip()


def out(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def fail(msg: str) -> int:
    out({"ok": False, "verdict": "STOP", "reason": msg})
    return 1


def git_root() -> Path | None:
    code, text = run_git("rev-parse", "--show-toplevel")
    if code != 0:
        return None
    return Path(text)


def current_branch() -> str:
    code, text = run_git("branch", "--show-current")
    return text if code == 0 and text else "DETACHED"


def parse_status() -> tuple[list[str], list[str]]:
    """→ (tracked_modified, untracked)."""
    code, text = run_git("status", "--porcelain=v1", "--untracked-files=all")
    if code != 0:
        return [], []
    tracked: list[str] = []
    untracked: list[str] = []
    for line in text.splitlines():
        if len(line) < 4:
            continue
        xy = line[:2]
        # porcelain: unstaged " M path" (пробел в [2]), staged "M path".
        path = line[3:] if line[2] == " " else line[2:]
        if " -> " in path:  # rename/copy: берём новое имя
            path = path.split(" -> ", 1)[1]
        if xy.strip() == "":
            continue
        if "?" in xy:
            untracked.append(path)
        else:
            tracked.append(path)
    return sorted(tracked), sorted(untracked)


def skip_worktree_files() -> list[str]:
    code, text = run_git("ls-files", "-v")
    if code != 0:
        return []
    return sorted(
        line[2:] for line in text.splitlines() if line.startswith(("S", "s"))
    )


def mode_changes() -> list[str]:
    code, text = run_git("diff", "--summary")
    if code != 0:
        return []
    return sorted(
        line.split()[-1] for line in text.splitlines() if " mode change " in line
    )


def classify(tracked: list[str], untracked: list[str],
             mine: list[str]) -> tuple[list[str], list[str]]:
    """→ (mine_paths, foreign_paths). Префиксное сравнение по нормализованным путям."""
    norm = [m.strip().rstrip("/") for m in mine if m.strip()]

    def is_mine(path: str) -> bool:
        for m in norm:
            if path == m or path.startswith(m + "/"):
                return True
        return False

    mine_paths = [p for p in tracked + untracked if is_mine(p)]
    foreign_paths = [p for p in tracked + untracked if not is_mine(p)]
    return sorted(mine_paths), sorted(foreign_paths)


def origin_ahead() -> tuple[int, int]:
    """→ (ahead, behind) текущей ветки относительно origin/main. -1 при ошибке."""
    run_git("fetch", "origin", "--quiet")
    code, text = run_git("rev-list", "--left-right", "--count",
                         "origin/main...HEAD")
    if code != 0:
        return -1, -1
    try:
        # --left-right: левая колонка — коммиты только в origin/main (behind),
        # правая — только в HEAD (ahead). Порядок важен.
        behind, ahead = (int(x) for x in text.split())
    except ValueError:
        return -1, -1
    return ahead, behind


def cmd_status(args) -> int:
    tracked, untracked = parse_status()
    mine_paths, foreign_paths = classify(tracked, untracked, args.mine)
    ahead, behind = origin_ahead()
    branch = current_branch()
    reasons: list[str] = []
    if branch == "main":
        reasons.append("текущая ветка main — нужна task-ветка")
    if foreign_paths:
        reasons.append(f"чужая грязь ({len(foreign_paths)}): "
                       + ", ".join(foreign_paths[:8]))
    if behind > 0:
        reasons.append(f"origin/main ушёл вперёд на {behind} — сначала merge")
    verdict = "STOP" if reasons else "GO"
    out({
        "ok": True,
        "verdict": verdict,
        "branch": branch,
        "mine": mine_paths,
        "foreign": foreign_paths,
        "skip_worktree": skip_worktree_files(),
        "mode_changes": mode_changes(),
        "origin_main": {"ahead": ahead, "behind": behind},
        "reasons": reasons,
    })
    return 0 if verdict == "GO" else 1


def cmd_stash_foreign(args) -> int:
    tracked, untracked = parse_status()
    _, foreign_paths = classify(tracked, untracked, args.mine)
    if not foreign_paths:
        out({"ok": True, "stashed": [], "note": "чужой грязи нет"})
        return 0
    # Stash только чужих путей (pathspec) — своё остаётся в дереве.
    # -u обязателен: untracked-пути иначе не stash-ятся (pathspec их не видит).
    code, _ = run_git("stash", "push", "-u", "-m", args.message, "--",
                      *foreign_paths)
    if code != 0:
        return fail("stash не удался — дерево не тронуто")
    out({"ok": True, "stashed": foreign_paths, "message": args.message})
    return 0


def cmd_pop(args) -> int:
    code, text = run_git("stash", "pop")
    if code != 0:
        return fail(f"stash pop не удался: {text[:200]}")
    out({"ok": True, "restored": True})
    return 0


def cmd_ship_check(args) -> int:
    """Гейты шага 0 /ship. Печатает тот же JSON, что и status."""
    return cmd_status(args)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tree-cop",
                                description="Коп чистоты дерева (см. docstring).")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_mine(sp):
        sp.add_argument("--mine", action="append", default=[],
                        help="свой путь/префикс сессии (можно несколько)")

    s = sub.add_parser("status", help="классификация грязи + вердикт")
    add_mine(s)
    s = sub.add_parser("stash-foreign", help="именованный stash только чужого")
    add_mine(s)
    s.add_argument("-m", "--message", default="tree-cop: чужая грязь",
                   help="сообщение stash")
    s = sub.add_parser("pop", help="вернуть stash копа")
    s = sub.add_parser("ship-check", help="гейты шага 0 /ship")
    add_mine(s)

    args = p.parse_args(argv)
    if args.cmd in ("status", "ship-check"):
        return cmd_ship_check(args)
    if args.cmd == "stash-foreign":
        return cmd_stash_foreign(args)
    if args.cmd == "pop":
        return cmd_pop(args)
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
