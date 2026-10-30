#!/usr/bin/env python3
"""canvas — машинная проекция planning-слоя Корабля (канва ЦСПиМ).

Схема строки (по стандарту УАС, письмо 051322d5e754):
  id, тип (roadmap|task|quest|goal|wait), название, зона/ведомство-владелец,
  ssot (файл + строка), статус, дата среза статуса, дедлайн/TTL, приоритет,
  для goal: критерии, kill + автор; wip-сессия, DoD-evidence, drift-флаги,
  доклад куда, арбитраж кем.

Правила (канон УАС/ЦУ):
  - канва НЕ источник правды: это проекция. Пишет только в свою зону.
  - значения как в источниках; отсутствие = None (в выводе прочерк, не ноль).
  - drift — сигнал, не вердикт.

Использование:
  canvas.py build   # собрать canvas.jsonl + canvas.md
  canvas.py show    # человеческая сводка из готового canvas.jsonl
"""
import json
import os
import re
import sys
import time

HOME = os.path.expanduser("~")
DOT = os.path.join(HOME, "dotfiles")
VAULT = os.path.join(HOME, "Projects/OpenCode-Vault")
STATE = os.path.join(HOME, ".local/state/opencode")
WAITS = os.path.join(HOME, ".local/share/ship-mail/waits.jsonl")
OUT_JSONL = os.path.join(DOT, "logs/canvas/canvas.jsonl")
OUT_MD = os.path.join(DOT, "logs/canvas/canvas.md")

STALE_DAYS = 7           # статус старше — drift-сигнал
ROADMAPS = [
    ("ДВ-Хаб", os.path.join(HOME, "Projects/dv-hub/docs/roadmap.md")),
    ("Серплюкс", os.path.join(HOME, "Projects/serp/docs/roadmap-2.0.md")),
    ("Ability Lab", os.path.join(HOME, "Projects/ability-lab/docs/specs/lab-roadmap-selfaudit.md")),
    ("AndroidOS", os.path.join(HOME, "Projects/AndroidOS/docs/roadmap.md")),
    ("dotfiles", os.path.join(DOT, "docs/specs")),
]


def _now():
    return time.time()


def _fmt(ts):
    return time.strftime("%Y-%m-%d", time.gmtime(ts)) if ts else None


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _age_days(ts):
    return None if not ts else round((_now() - ts) / 86400, 1)


def _row(**kw):
    base = {
        "id": None, "type": None, "title": None, "owner": None, "ssot": None,
        "status": None, "status_date": None, "deadline_or_ttl": None,
        "priority": None, "criteria": None, "kill": None, "kill_author": None,
        "wip_session": None, "dod_evidence": None, "drift": [],
        "report_to": "ЦУ", "arbitration": "ЦУ/владелец",
    }
    base.update(kw)
    return base


# ---------- источники ----------

def from_waits():
    rows = []
    if not os.path.exists(WAITS):
        return rows
    for line in open(WAITS, encoding="utf-8"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("done"):
            continue
        since_ts = d.get("since_ts")
        ttl = d.get("ttl_hours")
        deadline = (since_ts + ttl * 3600) if (since_ts and ttl) else None
        drift = []
        if deadline and _now() > deadline:
            drift.append("просрочен")
        if not ttl:
            drift.append("ожидание без TTL")
        rows.append(_row(
            id=f"wait:{d.get('id')}", type="wait", title=d.get("what"),
            owner=d.get("who_owes"), ssot="~/.local/share/ship-mail/waits.jsonl",
            status="в ожидании", status_date=_fmt(since_ts),
            deadline_or_ttl=f"{ttl}ч" if ttl else None,
            wip_session=d.get("who_waits"), drift=drift,
        ))
    return rows


def from_goals():
    rows = []
    agg = os.path.join(STATE, "goal.json")
    if os.path.exists(agg):
        try:
            d = json.load(open(agg, encoding="utf-8"))
        except Exception:
            d = {}
        if d:
            rows.append(_row(
                id="goal:aggregate", type="goal", title=d.get("objective"),
                owner="(агрегат)", ssot="~/.local/state/opencode/goal.json",
                status=d.get("status"), status_date=(d.get("updated_at") or "")[:10] or None,
                criteria=d.get("criteria") or None, kill=d.get("kill") or None,
                dod_evidence=(d.get("evidence") or None),
                drift=["агрегат: один слот на все сессии (Р-042)"] if d.get("status") == "active" else [],
            ))
    gdir = os.path.join(STATE, "goals")
    if os.path.isdir(gdir):
        for name in sorted(os.listdir(gdir)):
            if not name.endswith(".json"):
                continue
            try:
                d = json.load(open(os.path.join(gdir, name), encoding="utf-8"))
            except Exception:
                continue
            sid = name[:-5].split("-")[0]
            rows.append(_row(
                id=f"goal:{name[:-5]}", type="goal", title=d.get("objective"),
                owner=sid, ssot=f"~/.local/state/opencode/goals/{name}",
                status=d.get("status"), status_date=(d.get("updated_at") or "")[:10] or None,
                criteria=d.get("criteria") or None, kill=d.get("kill") or None,
                wip_session=sid, dod_evidence=(d.get("evidence") or None),
                drift=["sidecar вне штата (ручной)"] if "note" in d else [],
            ))
    return rows


def _md_rows(path):
    out = []
    if not os.path.exists(path):
        return out
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        if line.startswith("|") and line.count("|") >= 4:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells and re.match(r"^\w+-\d+(\.\d+)*$", cells[0]) and cells[0].split("-")[0].isalpha():
                out.append((n, cells))
    return out


def from_quests():
    rows = []
    p = os.path.join(VAULT, "11-Quests/quests.md")
    for n, cells in _md_rows(p):
        rows.append(_row(
            id=f"quest:{cells[0]}", type="quest", title=cells[1][:120],
            owner=cells[3] if len(cells) > 3 else None,
            ssot=f"11-Quests/quests.md:{n}", status=cells[2] if len(cells) > 2 else None,
            status_date=None,
            drift=[],
        ))
    return rows


def from_tasks():
    rows = []
    p = os.path.join(VAULT, "TASKS.md")
    for n, cells in _md_rows(p):
        status = None
        prio = None
        if len(cells) > 2:
            status = cells[2][:40]
        if len(cells) > 3:
            prio = cells[3][:20]
        rows.append(_row(
            id=f"task:{cells[0]}", type="task", title=cells[1][:120],
            owner="ЦУ", ssot=f"TASKS.md:{n}", status=status, priority=prio,
            status_date=None,
            drift=[],
        ))
    return rows


def from_roadmaps():
    rows = []
    for name, path in ROADMAPS:
        if os.path.isdir(path):
            ts = _mtime(path)
            rows.append(_row(
                id=f"roadmap:{name}", type="roadmap", title=f"роадмепы {name} (каталог)",
                owner=name, ssot=path.replace(HOME, "~"), status="ведётся",
                status_date=_fmt(ts),
                drift=["нет свода: статус не читается машиной"] if True else [],
            ))
            continue
        ts = _mtime(path)
        if not ts:
            continue
        rows.append(_row(
            id=f"roadmap:{name}", type="roadmap", title=f"роадмеп {name}",
            owner=name, ssot=path.replace(HOME, "~"), status="есть",
            status_date=_fmt(ts),
            drift=[f"статус старше {STALE_DAYS} дней"] if (ts and (_age_days(ts) or 0) > STALE_DAYS) else [],
        ))
    return rows


def from_sources():
    """Сигналы уровня источника — там, где построчная дата статуса отсутствует."""
    rows = []
    tasks = os.path.join(VAULT, "TASKS.md")
    age = _age_days(_mtime(tasks))
    if age is not None:
        rows.append(_row(
            id="source:TASKS.md", type="source", title="Реестр TASKS.md",
            owner="ЦУ", ssot="TASKS.md", status="не обновлялся",
            status_date=_fmt(_mtime(tasks)),
            drift=[f"источник не обновлялся {age} дн (порог {STALE_DAYS})"] if age > STALE_DAYS else [],
        ))
    rows.append(_row(
        id="source:duplicate-registries", type="source",
        title="Дубли реестров: TASKS.md / 11-Quests/quests.md / Deck/_gen/quests_data.py",
        owner="ЦУ", ssot="несколько", status="не сведены",
        drift=["дубль SSOT: один класс данных в трёх местах"],
    ))
    rows.append(_row(
        id="source:decision-queue", type="source", title="Очередь решений (decision-queue)",
        owner="плагин (глобал)", ssot="~/.local/state/opencode/decision-queue/cards",
        status="растёт", drift=["нет TTL/архива", "нет владельца очереди"],
    ))
    return rows


def collect():
    rows = from_sources() + from_roadmaps() + from_tasks() + from_quests() + from_goals() + from_waits()
    # сквозной drift: две цели в одном goal-слое
    active = [r for r in rows if r["type"] == "goal" and r["status"] == "active"]
    if len(active) > 1:
        for r in active:
            r["drift"].append(f"две+ активных цели в слое ({len(active)})")
    return rows


def build():
    rows = collect()
    os.makedirs(os.path.dirname(OUT_JSONL), exist_ok=True)
    with open(OUT_JSONL, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    by_type = {}
    for r in rows:
        by_type.setdefault(r["type"], 0)
        by_type[r["type"]] += 1
    drifted = [r for r in rows if r["drift"]]
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("# Канва планирования (проекция, не источник правды)\n\n")
        f.write(f"собрано: {time.strftime('%Y-%m-%d %H:%M')} · строк: {len(rows)}\n\n")
        f.write("## Состав\n\n")
        for t, c in sorted(by_type.items()):
            f.write(f"- {t}: {c}\n")
        f.write(f"\n## Сигналы дрейфа ({len(drifted)})\n\n")
        for r in drifted:
            f.write(f"- [{r['type']}] {str(r['title'])[:70]} — {'; '.join(r['drift'])}\n")
    print(f"CANVAS rows={len(rows)} by_type={by_type} drift={len(drifted)}")
    print(f"-> {OUT_JSONL}")
    print(f"-> {OUT_MD}")
    return 0


def show():
    if not os.path.exists(OUT_MD):
        print("канвы нет — собери: canvas.py build")
        return 1
    print(open(OUT_MD, encoding="utf-8").read())
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    return {"build": build, "show": show}.get(cmd, build)()


if __name__ == "__main__":
    raise SystemExit(main())
