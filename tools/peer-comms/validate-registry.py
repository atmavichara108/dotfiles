#!/usr/bin/env python3
"""Валидатор peer-registry: живость сессий + существование агентов.

Сопровождает letter.sh (peer-mail-loss-20261024): реестр — единственный
источник адресов, но строки в нём протухают. Скрипт по каждой строке-
ведомству peer-registry.md проверяет:

  1. сессия жива          — `opencode api get /api/session/<id>` вернул data.id
  2. агент существует     — <repo>/.opencode/agent/<agent>.md или
                            ~/.config/opencode/agent/<agent>.md
                            (repo — колонка «Каталог», ~ разворачивается;
                             агент нормализуется как в letter.sh:
                             lower + точки -> дефисы)
  пустой агент («—», «— (агент не назначен)», «не назначен») — отдельный
  статус NO-AGENT, а не ошибка «агент не найден».

Вывод: таблица Ведомство | Сессия | Агент | Статус. Только метаданные,
никаких секретов (канон репо). Exit: 0 — всё OK, 1 — есть не-OK.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_REGISTRY = Path.home() / "Projects/OpenCode-Vault/04-Memory/peer-registry.md"
GLOBAL_AGENT_DIR = Path.home() / ".config/opencode/agent"
REPO_AGENT_DIRNAME = ".opencode/agent"

STATUS_OK = "OK"
STATUS_DEAD = "DEAD-SESSION"
STATUS_NO_AGENT = "NO-AGENT"
STATUS_NOT_FOUND = "AGENT-NOT-FOUND"


def normalize_agent(raw: str) -> str:
    """Нормализация имени агента как в letter.sh: lower, '*' прочь, точки -> дефисы."""
    v = raw.strip().replace("*", "").strip()
    return v.lower().replace(".", "-") if v else ""


def agent_is_empty(raw: str) -> bool:
    """Пустые значения реестра: '', '-', '—', '–', «Агент», «не назначен»."""
    v = raw.strip().replace("*", "").strip()
    if not v or v == "Агент" or re.fullmatch(r"[-—–]+", v):
        return True
    return "не назнач" in v.lower()


def repo_agent_exists(agent: str, catalog: str) -> bool:
    """Агент есть в каталоге ведомства или в глобальном слое OpenCode."""
    if not agent:
        return False
    repo_dir = Path(os.path.expanduser(catalog.strip())) if catalog.strip() else None
    candidates = []
    if repo_dir.is_dir():
        candidates.append(repo_dir / REPO_AGENT_DIRNAME / f"{agent}.md")
    candidates.append(GLOBAL_AGENT_DIR / f"{agent}.md")
    return any(p.is_file() for p in candidates)


def session_alive(sid: str) -> bool:
    """Живая сессия: API вернул data.id (fail-closed: ошибка/пусто = мертва)."""
    try:
        proc = subprocess.run(
            ["opencode", "api", "get", f"/api/session/{sid}"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if proc.returncode != 0:
        return False
    try:
        data = json.loads(proc.stdout).get("data")
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and str(data.get("id", "")).startswith("ses")


def registry_rows(path: Path) -> list[tuple[str, str, str, str]]:
    """Строки ведомств: (Ведомство, SessionID, Агент_raw, Каталог)."""
    rows: list[tuple[str, str, str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.split("|")]
        # [ '', Ведомство, SessionID, Агент, Каталог, Роль, '' ]
        if len(cols) < 6 or not cols[2].startswith("ses_"):
            continue
        rows.append((cols[1], cols[2], cols[3], cols[4]))
    return rows


def main() -> int:
    reg = Path(os.environ.get("PEER_REGISTRY", str(DEFAULT_REGISTRY)))
    if not reg.is_file():
        print(f"Error: реестр не найден: {reg}", file=sys.stderr)
        return 1

    widths = (24, 34, 16, 16)
    print(f"{'Ведомство':<{widths[0]}} | {'Сессия':<{widths[1]}} | "
          f"{'Агент':<{widths[2]}} | Статус")
    print("-" * (sum(widths) + 9))

    bad = 0
    for name, sid, agent_raw, catalog in registry_rows(reg):
        agent_disp = agent_raw.replace("*", "").strip() or "—"
        alive = session_alive(sid)
        if not alive:
            status = STATUS_DEAD
        else:
            if agent_is_empty(agent_raw):
                status = STATUS_NO_AGENT
            else:
                agent = normalize_agent(agent_raw)
                status = (STATUS_OK if repo_agent_exists(agent, catalog)
                          else STATUS_NOT_FOUND)
        if status != STATUS_OK:
            bad += 1
        print(f"{name[:widths[0]]:<{widths[0]}} | {sid:<{widths[1]}} | "
              f"{agent_disp[:widths[2]]:<{widths[2]}} | {status}")

    total = len(registry_rows(reg))
    print("-" * (sum(widths) + 9))
    print(f"Итого: {total} ведомств, не-OK: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
