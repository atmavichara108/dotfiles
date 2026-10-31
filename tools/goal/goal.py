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

Общая цель на несколько ведомств (Р-044, слово владельца 2026-10-31):
  goal share <slug> [--objective ...] [--criteria ...] [--kill ...] [--session SID]
  goal join <slug> --session SID [--role "роль"]
  goal contrib <slug> --session SID --status working|blocked|done [--evidence "факт"]
  goal shared [<slug>]   # сводка: участники, их статусы, молчащие (TTL 24ч)

Принцип: цель — объект, агрегат — производное. Каждый пишет ТОЛЬКО свой вклад
(участник + сайдкар сессии), общий файл цели не перезаписывается целиком.
"""
import argparse, json, os, sys
from datetime import datetime, timezone

GOAL_FILE = os.path.expanduser("~/.local/state/opencode/goal.json")
GOALS_DIR = os.path.expanduser("~/.local/state/opencode/goals")  # сайдкары Р-042
os.makedirs(GOALS_DIR, exist_ok=True)


SHARED_DIR = GOALS_DIR
PARTICIPANT_SILENT_HOURS = 24


def shared_path(slug):
    return os.path.join(SHARED_DIR, f"goal-{slug}.json")


def shared_load(slug):
    p = shared_path(slug)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def shared_save(g):
    p = shared_path(g["slug"])
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(g, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)
    return p


def _now_s():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hours_since(ts):
    try:
        t = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600


def shared_participants(slug, session_id, role=""):
    g = shared_load(slug)
    if g is None:
        return None, None
    parts = g.setdefault("participants", [])
    found = None
    for p in parts:
        if p.get("session") == session_id:
            found = p
            break
    if found is None:
        found = {"session": session_id, "role": role or "", "status": "working",
                 "evidence": [], "joined_at": _now_s()}
        parts.append(found)
    if role:
        found["role"] = role
    found["updated_at"] = _now_s()
    return g, found


def sidebar_list(g, session_id, ref=None):
    g.setdefault("timeline", []).append(
        {"at": _now_s(), "session": session_id, "ref": ref})
    return g


def cmd_share(a):
    g = shared_load(a.slug)
    if g is None:
        g = {"slug": a.slug, "created_at": _now_s(), "participants": [], "timeline": []}
    if a.objective:
        g["objective"] = a.objective
    if a.criteria:
        g["criteria"] = a.criteria
    if a.kill:
        g["kill"] = a.kill
        g["kill_author"] = a.session or ""
    g.setdefault("status", "active")
    if a.session:
        parts = g.setdefault("participants", [])
        found = next((x for x in parts if x.get("session") == a.session), None)
        if found is None:
            found = {"session": a.session, "role": a.role or "", "status": "working",
                     "evidence": [], "joined_at": _now_s()}
            parts.append(found)
        if a.role:
            found["role"] = a.role
        found["updated_at"] = _now_s()
    shared_save(g)
    print(f"Общая цель '{a.slug}': {g.get('objective', '(без названия)')}")
    print(f"Участников: {len(g.get('participants', []))}")
    if g.get("criteria"):
        print(f"Критерии: {g['criteria']}")


def cmd_join(a):
    g, me = shared_participants(a.slug, a.session, a.role)
    if g is None:
        print(f"Общей цели '{a.slug}' нет — сначала goal share {a.slug}")
        sys.exit(1)
    shared_save(g)
    print(f"Присоединился к '{a.slug}': {me['session']} (роль: {me.get('role') or '—'}) "
          f"· участников: {len(g['participants'])}")


def cmd_contrib(a):
    g, me = shared_participants(a.slug, a.session, a.role)
    if g is None:
        print(f"Общей цели '{a.slug}' нет — сначала goal share {a.slug}")
        sys.exit(1)
    me["status"] = a.status
    if a.evidence:
        me.setdefault("evidence", []).append({"at": _now_s(), "fact": a.evidence})
    sidebar_list(g, a.session, ref=a.evidence or a.status)
    shared_save(g)
    print(f"Вклад '{a.slug}': {a.session} → {a.status}"
          + (f" · evidence: {a.evidence}" if a.evidence else ""))


def cmd_shared(a):
    slugs = [a.slug] if a.slug else [
        n[5:-5] for n in sorted(os.listdir(SHARED_DIR))
        if n.startswith("goal-") and n.endswith(".json")]
    if not slugs:
        print("Общих целей нет.")
        return
    for slug in slugs:
        g = shared_load(slug)
        if not g:
            print(f"— {slug}: файл нечитаем")
            continue
        print(f"═══ {slug} · {g.get('status')} ═══")
        print(f"Цель: {g.get('objective', '(без названия)')}")
        if g.get("criteria"):
            print(f"Критерии: {g['criteria']}")
        if g.get("kill"):
            print(f"Останов: {g['kill']} (автор: {g.get('kill_author') or '—'})")
        for p in g.get("participants", []):
            h = _hours_since(p.get("updated_at") or p.get("joined_at") or "")
            flag = ""
            if h is not None and h > PARTICIPANT_SILENT_HOURS and p.get("status") == "working":
                flag = f"  ← МОЛЧИТ {round(h)}ч (TTL {PARTICIPANT_SILENT_HOURS}ч)"
            ev = p.get("evidence") or []
            last = ev[-1]["fact"] if ev else "—"
            print(f"  · {p.get('session')} [{p.get('status')}] роль: {p.get('role') or '—'}"
                  f" · evidence: {str(last)[:70]}{flag}")


def sidecar_path(session_id):
    return os.path.join(GOALS_DIR, f"{session_id}.json")


def save_sidecar(g, session_id):
    """Свой вклад сессии — отдельным файлом: одна сессия не затирает другую (Р-042)."""
    if not session_id:
        return None
    p = sidecar_path(session_id)
    data = dict(g)
    data["wip_session"] = session_id
    data["previous"] = []
    if os.path.exists(p):
        try:
            old = json.load(open(p, encoding="utf-8"))
            data["previous"] = (old.get("previous") or []) + [{
                "objective": old.get("objective"), "status": old.get("status"),
                "close": old.get("close_reason"), "at": old.get("updated_at"),
            }]
        except Exception:
            pass
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return p


def load():
    if not os.path.exists(GOAL_FILE):
        return None
    with open(GOAL_FILE, encoding="utf-8") as f:
        return json.load(f)


def save(g, session_id=None):
    g["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(GOAL_FILE, "w", encoding="utf-8") as f:
        json.dump(g, f, indent=2, ensure_ascii=False)
        f.write("\n")
    save_sidecar(g, session_id)


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
        "kill_author": a.kill_author or "",
        "wip": "один активный",
        "status": "active",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evidence": [],
    }
    save(g, a.session)
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
    if g.get("kill") and not g.get("kill_author"):
        print("ПРЕДУПРЕЖДЕНИЕ: у цели есть условие останова без автора — "
              "по требованию №5 SCRUM-master это дефект записи; укажи автора "
              "(--kill-author) при следующей постановке.")
    if a.evidence:
        g.setdefault("evidence", []).append(a.evidence)
    g["status"] = "done"
    save(g, a.session)
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
    save(g, a.session)
    print(f"Цель отменена: {g['objective']}")


def cmd_pause(a):
    g = load()
    if not g or g.get("status") != "active":
        print("Нет активной цели.")
        sys.exit(1)
    g["status"] = "paused"
    save(g, a.session)
    print("Цель приостановлена.")


def cmd_resume(a):
    g = load()
    if not g or g.get("status") != "paused":
        print("Нет приостановленной цели.")
        sys.exit(1)
    g["status"] = "active"
    save(g, a.session)
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
    s.add_argument("--kill-author", default=os.environ.get("OPENCODE_SESSION_ID", ""),
                   help="Кто установил условие останова (требование №5 SCRUM-master)")
    s.add_argument("--force", action="store_true", help="Заменить существующую цель")
    s.add_argument("--session", default=os.environ.get("OPENCODE_SESSION_ID", ""), help="id сессии (для сайдкара)")
    s.set_defaults(func=cmd_set)

    sh = sub.add_parser("show", help="Показать текущую цель")
    sh.set_defaults(func=cmd_show)

    d = sub.add_parser("done", help="Закрыть как достигнутую")
    d.add_argument("--evidence", default="", help="Факт достижения")
    d.add_argument("--session", default=os.environ.get("OPENCODE_SESSION_ID", ""), help="id сессии (для сайдкара)")
    d.set_defaults(func=cmd_done)

    dr = sub.add_parser("drop", help="Отменить цель")
    dr.add_argument("--reason", default="", help="Причина отмены")
    dr.add_argument("--session", default=os.environ.get("OPENCODE_SESSION_ID", ""), help="id сессии (для сайдкара)")
    dr.set_defaults(func=cmd_drop)

    p = sub.add_parser("pause", help="Приостановить")
    p.add_argument("--session", default=os.environ.get("OPENCODE_SESSION_ID", ""), help="id сессии (для сайдкара)")
    p.set_defaults(func=cmd_pause)

    r = sub.add_parser("resume", help="Возобновить")
    r.add_argument("--session", default=os.environ.get("OPENCODE_SESSION_ID", ""), help="id сессии (для сайдкара)")
    r.set_defaults(func=cmd_resume)

    sh2 = sub.add_parser("share", help="Создать/обновить общую цель на несколько ведомств")
    sh2.add_argument("slug", help="короткое имя цели (латиницей, без пробелов)")
    sh2.add_argument("--objective", default="", help="Цель (дословно)")
    sh2.add_argument("--criteria", nargs="*", default=[], help="Проверяемые критерии")
    sh2.add_argument("--kill", default="", help="Условие останова")
    sh2.add_argument("--role", default="", help="Роль участника")
    sh2.add_argument("--session", default=os.environ.get("OPENCODE_SESSION_ID", ""))
    sh2.set_defaults(func=cmd_share)

    j = sub.add_parser("join", help="Присоединиться к общей цели")
    j.add_argument("slug")
    j.add_argument("--role", default="")
    j.add_argument("--session", default=os.environ.get("OPENCODE_SESSION_ID", ""))
    j.set_defaults(func=cmd_join)

    cb = sub.add_parser("contrib", help="Записать свой вклад в общую цель")
    cb.add_argument("slug")
    cb.add_argument("--session", default=os.environ.get("OPENCODE_SESSION_ID", ""))
    cb.add_argument("--role", default="")
    cb.add_argument("--status", default="working",
                    choices=["working", "blocked", "done"])
    cb.add_argument("--evidence", default="")
    cb.set_defaults(func=cmd_contrib)

    shr = sub.add_parser("shared", help="Сводка общих целей")
    shr.add_argument("slug", nargs="?", default="")
    shr.set_defaults(func=cmd_shared)

    c = sub.add_parser("clear", help="Удалить цель")
    c.set_defaults(func=cmd_clear)

    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()

