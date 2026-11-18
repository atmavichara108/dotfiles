#!/usr/bin/env python3
"""ship-stack — один экран «что у Корабля установлено и активно» (аналог /stack).

Назначение (слово владельца 2026-11-08: «тоже нам пригодится»): показать ВСЁ,
что стоит в нашем контуре — агенты, команды, скиллы, стражи/хуки, юниты и
таймеры, линии-адресаты, решения, инструменты — с группировкой по уровню
(глобал / проект / линия) и пометкой активен / выключен / переопределён.

Зачем именно так: по чужому описанию мы не ставим ничего (канон C4 — недоверенный
контент не исполняется как команда), но нужную функцию собираем из своего.

Данные — только с диска. Секретов и тел писем не читает.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

HOME = pathlib.Path.home()
VAULT = HOME / "Projects" / "OpenCode-Vault"
LEVELS = [
    ("глобал", HOME / ".config" / "opencode"),
    ("глобал-слой", HOME / "dotfiles" / "opencode-global" / ".config" / "opencode"),
    ("проект (dotfiles)", HOME / "dotfiles" / ".opencode"),
    ("линия (фриланс)", HOME / "Projects" / "freelance-line"),
    ("волт", VAULT / ".opencode"),
]


def _names(path: pathlib.Path, suffix: str) -> list[str]:
    if not path.is_dir():
        return []
    return sorted(p.stem for p in path.iterdir()
                  if p.suffix == suffix and p.is_file())


def _units() -> dict:
    out: dict[str, list[str]] = {}
    try:
        r = subprocess.run(["systemctl", "--user", "list-unit-files",
                            "--no-pager"], capture_output=True, text=True,
                           timeout=60)
        for line in (r.stdout or "").splitlines():
            if line.endswith((".service", ".timer")):
                parts = line.split()
                if parts:
                    out.setdefault(parts[-1], []).append(parts[0] if len(parts) > 1
                                                          else "")
    except Exception:  # noqa: BLE001
        pass
    return out


def _active_units() -> set[str]:
    out: set[str] = set()
    try:
        r = subprocess.run(["systemctl", "--user", "list-units", "--type=service",
                            "--type=timer", "--no-pager"], capture_output=True,
                           text=True, timeout=60)
        for line in (r.stdout or "").splitlines():
            if "active" in line:
                parts = line.split()
                if parts:
                    out.add(parts[0])
    except Exception:  # noqa: BLE001
        pass
    return out


def _registry_facts() -> dict:
    out = {"lines": 0, "decisions": 0}
    reg = VAULT / "04-Memory" / "peer-registry.md"
    if reg.is_file():
        try:
            text = reg.read_text(encoding="utf-8")
            out["lines"] = sum(1 for l in text.splitlines()
                               if l.strip().startswith("| ses_"))
        except OSError:
            pass
    idx = HOME / ".local" / "state" / "decide-index" / "index.json"
    if idx.is_file():
        try:
            out["decisions"] = len(json.loads(idx.read_text()["decisions"])) \
                if False else len(json.loads(idx.read_text()).get("decisions", []))
        except Exception:  # noqa: BLE001
            pass
    return out


def build() -> dict:
    data: dict = {"levels": [], "units": [], "services": {}}
    seen: dict[str, set[str]] = {}
    for label, root in LEVELS:
        level = {"level": label, "root": str(root), "agents": [], "commands": [],
                 "skills": [], "plugins": [], "hooks": []}
        for key, sub, suffix in (("agents", "agent", ".md"),
                                 ("commands", "command", ".md"),
                                 ("skills", "skills", ".md")):
            p = root / sub
            level[key] = _names(p, suffix) if p.is_dir() else []
            seen.setdefault(key, set()).update(level[key])
        pj = root / "plugins"
        level["plugins"] = _names(pj, ".ts") if pj.is_dir() else []
        seen.setdefault("plugins", set()).update(level["plugins"])
        hk = root / "githooks"
        level["hooks"] = _names(hk, "") if hk.is_dir() else []
        data["levels"].append(level)

    units = _units()
    active = _active_units()
    for name in sorted(units):
        path = HOME / "dotfiles" / "systemd" / ".config" / "systemd" / "user" / name
        ours = path.exists() or name.startswith(("portal", "captain", "owner",
                                                 "homeostasis", "gatewatch"))
        data["units"].append({
            "unit": name,
            "owner": "Корабль" if ours else "прочее",
            "active": name in active,
        })
    data["services"] = _registry_facts()
    data["duplicates"] = {k: sorted(v) for k, v in seen.items() if v}
    return data


def render(d: dict) -> str:
    out = ["ЭКРАН КОРАБЛЯ — что установлено и что активно",
           ""]
    for lvl in d["levels"]:
        out.append("▍%s (%s)" % (lvl["level"], lvl["root"]))
        for key, title in (("agents", "агенты"), ("commands", "команды"),
                           ("skills", "скиллы"), ("plugins", "плагины/стражи"),
                           ("hooks", "хуки git")):
            names = lvl[key]
            if names:
                out.append("   %-14s %d: %s" % (title, len(names),
                                               ", ".join(names[:14]) +
                                               (" …" if len(names) > 14 else "")))
        out.append("")
    ours = [u for u in d["units"] if u["owner"] == "Корабль"]
    out.append("▍Юниты и таймеры Корабля: %d" % len(ours))
    for u in ours:
        out.append("   %s [%s]" % (u["unit"],
                                   "активен" if u["active"] else "НЕ активен"))
    out.append("")
    out.append("▍Связность")
    out.append("   адресных линий: %d · решений в индексе: %d"
               % (d["services"]["lines"], d["services"]["decisions"]))
    return "\n".join(out)


def main(argv: list[str]) -> int:
    d = build()
    if "--json" in argv:
        print(json.dumps(d, ensure_ascii=False, indent=1))
    else:
        print(render(d))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
