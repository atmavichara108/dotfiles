#!/usr/bin/env python3
"""follower — «Следопыт»: read-only агрегат постановок (мандат ЦУ 2026-11-01).

Один экран «где всё и на какой стадии»: читает существующие файлы
(quests, TASKS, waits, session-log, decision-registry, goals), каждой строке
даёт ровно одно из четырёх состояний (зафиксировано / в работе / ждёт слова /
закрыто), поднимает сигналы стагнации, печатает одну страницу + одну
машиночитаемую строку. НИЧЕГО не пишет в источники (Р-056).

Состояния (канон ЦУ):
  зафиксировано — записано, не начато (ready/backlog/parked/Р-Д-строка решения)
  в работе      — активно (active/in_progress/🟡)
  ждёт слова    — ожидание чужого действия/слова (blocked/locked/waits/paused)
  закрыто       — завершено с evidence (done/dropped/✅/запись решения в каноне)

Сигналы (пороги в ~/.local/state/opencode/follower.json):
  wait_hours (48)  — ожидание старше порога
  idle_days  (7)   — «в работе», но не упоминалось в session-log столько дней
  overdue          — TTL ожидания исчерпан (сразу, порог не нужен)

Строка без состояния = дефект агрегатора → секция UNSTATED, rc=2.

Использование:
  follower.py              # страница для человека
  follower.py --json-line   # + одна машиночитаемая строка в stdout
  rc: 0 ок · 2 есть UNSTATED · 1 ошибка источника
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sys

HOME = os.path.expanduser("~")
VAULT = os.path.join(HOME, "Projects/OpenCode-Vault")
QUESTS = os.path.join(VAULT, "11-Quests/quests.md")
TASKS = os.path.join(VAULT, "TASKS.md")
REGISTRY = os.path.join(VAULT, "docs/org/decision-registry.md")
SESSION_LOG = os.path.join(VAULT, "04-Memory/session-log")
WAITS = os.path.join(HOME, ".local/share/ship-mail/waits.jsonl")
GOALS = os.path.join(HOME, ".local/state/opencode/goal.json")
GOAL_DIR = os.path.join(HOME, ".local/state/opencode/goals")
CONF = os.path.join(HOME, ".local/state/opencode/follower.json")

ST_FIXED = "зафиксировано"
ST_WORK = "в работе"
ST_WAIT = "ждёт слова"
ST_DONE = "закрыто"
STATES = (ST_FIXED, ST_WORK, ST_WAIT, ST_DONE)

DEFAULT_CONF = {"wait_hours": 48, "idle_days": 7}


def load_conf():
    try:
        with open(CONF, encoding="utf-8") as f:
            c = json.load(f)
        return {**DEFAULT_CONF, **c}
    except FileNotFoundError:
        os.makedirs(os.path.dirname(CONF), exist_ok=True)
        with open(CONF, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONF, f, ensure_ascii=False, indent=2)
        return dict(DEFAULT_CONF)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONF)


def row(id_, source, title, state, owner="", note="", evidence=""):
    return {"id": id_, "source": source, "title": title, "state": state,
            "owner": owner, "note": note, "evidence": evidence}


def read_text(path, problems):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        problems.append(f"{path}: {e}")
        return ""


# ---------- парсеры источников ----------

QUEST_STATUS = {"active": ST_WORK, "ready": ST_FIXED, "parked": ST_FIXED,
                "locked": ST_WAIT, "done": ST_DONE, "closed": ST_DONE,
                "cancelled": ST_DONE}
# locked: квест ждёт преусловия (слово владельца, другой квест) — это «ждёт слова»
# по построению: locked без условия ожидания в реестре не встречается.


def parse_quests(problems, unstated):
    rows = []
    text = read_text(QUESTS, problems)
    if not text and not problems:
        return rows
    for line in text.splitlines():
        m = re.match(r"^\|\s*\*{0,2}(Q-[\d.]+)\*{0,2}\s*\|(.+)$", line)
        if not m:
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        if len(cells) < 5:
            unstated.append(f"quests:{m.group(1)}: {line[:70]}")
            continue
        qid, title, status = cells[0].strip("*"), cells[1], cells[2].lower()
        owner = cells[3] if len(cells) > 3 else ""
        state = QUEST_STATUS.get(status)
        if state is None:
            unstated.append(f"quests:{qid}: неизвестный статус {cells[2]!r}")
            continue
        rows.append(row(qid, "quests", title, state, owner=owner,
                        note=f"статус:{status}"))
    return rows


# секции TASKS.md: заголовок секции задаёт статус строк внутри
TASK_SECTION = {"🟡": ST_WORK, "⛔": ST_WAIT, "🟤": ST_FIXED,
                "✅": ST_DONE, "➖": ST_DONE}


def parse_tasks(problems, unstated):
    rows = []
    text = read_text(TASKS, problems)
    if not text and not problems:
        return rows
    section = None
    for line in text.splitlines():
        h = re.match(r"^##\s+(\S+)\s+(.*)$", line)
        if h:
            section = h.group(1)
            continue
        m = re.match(r"^\|\s*(T-\d+)\s*\|(.+)$", line)
        if not m:
            continue
        state = TASK_SECTION.get(section) if section else None
        tid = m.group(1)
        if state is None:
            unstated.append(f"tasks:{tid}: секция {section!r} не распознана")
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        title = re.sub(r"\*\*", "", cells[1]) if len(cells) > 1 else ""
        owner = cells[3] if len(cells) > 3 else ""
        ev = ""
        if state == ST_DONE:
            dm = re.search(r"[Dd]one\s+(\d{4}-\d{2}-\d{2})", title)
            ev = dm.group(0) if dm else "запись в секции Done"
        rows.append(row(tid, "TASKS", title, state, owner=owner,
                        note=f"секция:{section}", evidence=ev))
    return rows


def parse_waits(problems, now):
    rows = []
    try:
        with open(WAITS, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                w = json.loads(line)
                age_h = (now - dt.datetime.fromisoformat(
                    w["since"].replace("Z", "+00:00")).timestamp()) / 3600 \
                    if "since" in w else None
                rows.append(row(w.get("id", "?"), "waits", w.get("what", ""),
                                ST_WAIT, owner=w.get("who_owes", ""),
                                note=f"age_h:{age_h:.0f}" if age_h is not None else "",
                                evidence=""))
                rows[-1]["age_h"] = age_h
                rows[-1]["ttl_hours"] = w.get("ttl_hours")
    except FileNotFoundError:
        problems.append(f"waits: {WAITS} нет")
    except json.JSONDecodeError as e:
        problems.append(f"waits: битая строка JSONL — {e}")
    return rows


def parse_decisions(problems, unstated):
    rows = []
    text = read_text(REGISTRY, problems)
    if not text and not problems:
        return rows
    for line in text.splitlines():
        m = re.match(r"^\|\s*(Р-Д-\d+)\s*\|(.+)$", line)
        if not m:
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        if len(cells) < 4:
            unstated.append(f"decisions:{m.group(1)}: {line[:70]}")
            continue
        rid, date = cells[0], cells[1]
        executor = cells[-1]
        # решение записано в канон-реестр = закрыто; исполнение — отдельные
        # линии (TASKS/quests), в строке решения статуса исполнения нет.
        rows.append(row(rid, "decisions", cells[2][:90], ST_DONE,
                        owner=executor, note=f"слово:{date}",
                        evidence="запись в decision-registry"))
    return rows


def parse_goals(problems, unstated):
    rows = []
    GOAL_STATUS = {"active": ST_WORK, "paused": ST_WAIT, "done": ST_DONE,
                   "dropped": ST_DONE}

    def one(path, fallback_id):
        try:
            with open(path, encoding="utf-8") as f:
                g = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            problems.append(f"goals {path}: {e}")
            return
        status = g.get("status", "")
        state = GOAL_STATUS.get(status)
        gid = g.get("slug") or g.get("storage", "").split("/")[-1] \
            or g.get("session") or fallback_id
        if state is None:
            unstated.append(f"goals:{gid}: неизвестный статус {status!r}")
            return
        ev = ""
        if state == ST_DONE:
            e = g.get("evidence")
            if isinstance(e, list) and e:
                ev = str(e[-1])[:70]
            elif isinstance(e, str) and e:
                ev = e[:70]
        r = row(str(gid), "goals", (g.get("objective") or "")[:90], state,
                note=f"статус:{status}", evidence=ev)
        if "updated_at" in g:
            r["updated_at"] = g["updated_at"]
        rows.append(r)

    if os.path.exists(GOALS):
        one(GOALS, "goal-aggregate")
    for p in sorted(glob.glob(os.path.join(GOAL_DIR, "*.json"))):
        one(p, os.path.basename(p))
    return rows


# ---------- сигналы стагнации ----------

def load_last_seen(problems):
    """ID -> дата последнего упоминания в session-log (из имени файла)."""
    last = {}
    files = sorted(glob.glob(os.path.join(SESSION_LOG, "*.md")))
    if not files:
        problems.append(f"session-log: {SESSION_LOG} пуст/нет")
        return last
    for path in files:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
        date = m.group(1) if m else "0000-00-00"
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        for pid in set(re.findall(r"\b(?:T-\d+|Q-[\d.]+|Р-Д-\d+)\b", text)):
            last[pid] = date  # файлы отсортированы: последнее упоминание побеждает
    return last


def signals(rows, last_seen, conf, now):
    out = []
    today = dt.date.fromtimestamp(now).isoformat()
    for r in rows:
        if r["source"] == "waits":
            age, ttl = r.get("age_h"), r.get("ttl_hours")
            if age is not None and ttl is not None and age > ttl:
                out.append({"id": r["id"], "reason":
                            f"просрочено ожидание {age:.0f}ч > TTL {ttl}ч"})
            elif age is not None and age > conf["wait_hours"]:
                out.append({"id": r["id"], "reason":
                            f"ожидание {age:.0f}ч > порога {conf['wait_hours']}ч"})
        elif r["state"] == ST_WORK and r["source"] in ("TASKS", "quests"):
            seen = last_seen.get(r["id"])
            if seen is None:
                out.append({"id": r["id"], "reason":
                            "в работе, но нет упоминаний в session-log"})
            else:
                idle = (dt.date.fromisoformat(today)
                        - dt.date.fromisoformat(seen)).days
                if idle > conf["idle_days"]:
                    out.append({"id": r["id"], "reason":
                                f"в работе, {idle}д без упоминаний "
                                f"(порог {conf['idle_days']}д)"})
        elif r["state"] == ST_WORK and r["source"] == "goals" \
                and r.get("updated_at"):
            try:
                upd = r["updated_at"][:10]
                idle = (dt.date.fromisoformat(today)
                        - dt.date.fromisoformat(upd)).days
                if idle > conf["idle_days"]:
                    out.append({"id": r["id"], "reason":
                                f"цель в работе, {idle}д без обновлений "
                                f"(порог {conf['idle_days']}д)"})
            except ValueError:
                pass
    return out


def half_done(rows, last_seen):
    """полпути: в работе и уже упоминалась — началась, но не закрыта."""
    return [r["id"] for r in rows
            if r["state"] == ST_WORK and r["id"] in last_seen]


def main():
    ap = argparse.ArgumentParser(description="Следопыт: read-only агрегат постановок")
    ap.add_argument("--json-line", action="store_true",
                    help="вывести одну машиночитаемую строку")
    args = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc).timestamp()
    conf = load_conf()
    problems, unstated = [], []
    rows = []
    rows += parse_quests(problems, unstated)
    rows += parse_tasks(problems, unstated)
    rows += parse_waits(problems, now)
    rows += parse_decisions(problems, unstated)
    rows += parse_goals(problems, unstated)
    if problems and not rows:
        print("FATAL: источники недоступны: " + "; ".join(problems),
              file=sys.stderr)
        return 1

    last_seen = load_last_seen(problems)
    sigs = signals(rows, last_seen, conf, now)
    half = half_done(rows, last_seen)

    by_state = {s: 0 for s in STATES}
    for r in rows:
        by_state[r["state"]] += 1

    # ---- страница для человека ----
    print("СЛЕДОПЫТ — где всё и на какой стадии")
    print("=" * 72)
    for s in (ST_WORK, ST_WAIT, ST_FIXED, ST_DONE):
        group = [r for r in rows if r["state"] == s]
        print(f"\n■ {s.upper()} ({len(group)})")
        for r in group:
            own = f" [{r['owner']}]" if r["owner"] else ""
            note = f" ({r['note']})" if r["note"] else ""
            ev = f" → evidence: {r['evidence']}" if r["evidence"] else ""
            print(f"  {r['source']} {r['id']}: {r['title'][:70]}{own}{note}{ev}")
    print(f"\n■ СИГНАЛЫ ({len(sigs)})")
    for s in sigs:
        print(f"  ⚠ {s['id']}: {s['reason']}")
    if half:
        print(f"\n■ ПОЛПУТИ — начато, не закрыто ({len(half)}): "
              + ", ".join(half[:12]) + ("…" if len(half) > 12 else ""))
    if unstated:
        print(f"\n■ UNSTATED — без состояния ({len(unstated)}) — дефект агрегатора")
        for u in unstated:
            print(f"  ✗ {u}")
    if problems:
        print(f"\n■ ПРОБЛЕМЫ ИСТОЧНИКОВ ({len(problems)})")
        for p in problems:
            print(f"  ! {p}")
    print(f"\nИтого строк: {len(rows)} · без состояния: {len(unstated)} · "
          f"сигналов: {len(sigs)}")

    if args.json_line:
        payload = {
            "ts": dt.datetime.fromtimestamp(
                now, dt.timezone.utc).isoformat(timespec="seconds"),
            "tool": "follower-0.1",
            "total": len(rows), "stated": len(rows) - len(unstated),
            "unstated": len(unstated),
            "by_state": by_state,
            "alerts": sigs,
            "half_done": half,
            "sources": [{"path": p, "ok": True} for p in
                        (QUESTS, TASKS, WAITS, REGISTRY)] +
                       [{"path": SESSION_LOG, "ok": not problems}],
        }
        print(json.dumps(payload, ensure_ascii=False))

    return 2 if unstated else 0


if __name__ == "__main__":
    sys.exit(main())
