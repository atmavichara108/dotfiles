#!/usr/bin/env python3
"""goal — cmdline-инвокатор для /goal (OpenCode 2.2.1+).

Позволяет ставить/смотреть/закрывать цель из headless-вызовов (opencode run),
где slash-команда /goal недоступна. Хранилище общее с /goal: ~/.local/state/opencode/goal.json.

Использование:
  goal set "objective" [--criteria "c1" "c2"] [--kill "условие"]
  goal show
  goal done [--evidence "факт"]
  goal drop [--reason "причина"]
  goal pause | goal resume
  goal clear  # удалить цель полностью (осторожно)
"""
import argparse, json, os, sys
from datetime import datetime, timezone

GOAL_FILE = os.path.expanduser("~/.local/state/opencode/goal.json")
os.makedirs(os.path.dirname(GOAL_FILE), exist_ok=True)


def load():
    if not os.path.exists(GOAL_FILE):
        return None
    with open(GOAL_FILE, encoding="utf-8") as f:
        return json.load(f)


def save(g):
    g["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(GOAL_FILE, "w", encoding="utf-8") as f:
        json.dump(g, f, indent=2, ensure_ascii=False)
        f.write("\n")


def cmd_set(a):
    g = load()
    if g and g.get("status") == "active":
        print(f"Уже есть активная цель: {g['objective']}")
        print("Заменить? (используй --force для принудительной замены)")
        if not a.force:
            sys.exit(1)
    g = {
        "objective": a.objective,
        "criteria": a.criteria or [],
        "kill": a.kill or "",
        "wip": "один активный",
        "status": "active",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evidence": [],
    }
    save(g)
    print(f"Цель поставлена: {g['objective']}")
    if g["criteria"]:
        print(f"Критерии: {g['criteria']}")
    if g["kill"]:
        print(f"Останов: {g['kill']}")


def cmd_show(a):
    g = load()
    if not g:
        print("Активной цели нет.")
        return
    print(f"Цель: {g['objective']}")
    print(f"Останов: {g.get('kill', '')}")
    print(f"Статус: {g.get('status', '?')}")
    print()
    print("Критерии:")
    for i, c in enumerate(g.get("criteria", []), 1):
        ev = g.get("evidence", [])
        checked = ev[i-1] if i-1 < len(ev) else "не проверено"
        print(f"  {i}. {c} — проверено: {checked}")
    if g.get("evidence"):
        print()
        print("Evidence:")
        for e in g["evidence"]:
            print(f"  - {e}")


def cmd_done(a):
    g = load()
    if not g or g.get("status") not in ("active", "paused"):
        print("Нет активной цели.")
        sys.exit(1)
    if a.evidence:
        g.setdefault("evidence", []).append(a.evidence)
    g["status"] = "done"
    save(g)
    print(f"Цель достигнута: {g['objective']}")
    if g.get("evidence"):
        print("Evidence:")
        for e in g["evidence"]:
            print(f"  - {e}")


def cmd_drop(a):
    g = load()
    if not g or g.get("status") not in ("active", "paused"):
        print("Нет активной цели.")
        sys.exit(1)
    g.setdefault("evidence", []).append(f"Отменено: {a.reason or 'без причины'}")
    g["status"] = "dropped"
    save(g)
    print(f"Цель отменена: {g['objective']}")


def cmd_pause(a):
    g = load()
    if not g or g.get("status") != "active":
        print("Нет активной цели.")
        sys.exit(1)
    g["status"] = "paused"
    save(g)
    print("Цель приостановлена.")


def cmd_resume(a):
    g = load()
    if not g or g.get("status") != "paused":
        print("Нет приостановленной цели.")
        sys.exit(1)
    g["status"] = "active"
    save(g)
    print("Цель возобновлена.")


def cmd_clear(a):
    if os.path.exists(GOAL_FILE):
        os.remove(GOAL_FILE)
        print("Цель удалена.")
    else:
        print("Активной цели нет.")


def main():
    ap = argparse.ArgumentParser(description="cmdline-инвокатор /goal")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("set", help="Поставить цель")
    s.add_argument("objective", help="Текст цели (дословно)")
    s.add_argument("--criteria", nargs="*", default=[], help="Проверяемые критерии")
    s.add_argument("--kill", default="", help="Условие останова")
    s.add_argument("--force", action="store_true", help="Заменить существующую цель")
    s.set_defaults(func=cmd_set)

    sh = sub.add_parser("show", help="Показать текущую цель")
    sh.set_defaults(func=cmd_show)

    d = sub.add_parser("done", help="Закрыть как достигнутую")
    d.add_argument("--evidence", default="", help="Факт достижения")
    d.set_defaults(func=cmd_done)

    dr = sub.add_parser("drop", help="Отменить цель")
    dr.add_argument("--reason", default="", help="Причина отмены")
    dr.set_defaults(func=cmd_drop)

    p = sub.add_parser("pause", help="Приостановить")
    p.set_defaults(func=cmd_pause)

    r = sub.add_parser("resume", help="Возобновить")
    r.set_defaults(func=cmd_resume)

    c = sub.add_parser("clear", help="Удалить цель")
    c.set_defaults(func=cmd_clear)

    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()

