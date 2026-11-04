#!/usr/bin/env python3
"""stuck — детектор тихо зависших (каркас v0.1, мандат ЦУ 2026-11-04).

Цель: видеть не «сколько дней прошло», а состояние+причину+следующий шаг
(Р-076: дни — справка, НЕ критерий). Источники — события: goals sidecar,
ship-mail ожидания, письма, коммиты. Скрипт read-only по источникам:
единственная запись — своя зона logs/stuck/.

Критерии прогрессии ещё пишет ЦСПМ (ждут ответов ИПТ/ХПФ), поэтому сейчас
каркас: модель данных, точки подключения, dry-run.

Использование:
  stuck.py build [--dry-run]   # собрать logs/stuck/stuck.jsonl + stuck.md
  stuck.py show
"""
import argparse
import glob
import json
import os
import subprocess
import time

HOME = os.path.expanduser("~")
STATE = os.path.join(HOME, ".local/state/opencode")
WAITS = os.path.join(HOME, ".local/share/ship-mail/waits.jsonl")
MAIL = os.path.join(HOME, ".local/share/ship-mail")
DOT = os.path.join(HOME, "dotfiles")
OUT_DIR = os.path.join(DOT, "logs/stuck")
OUT_JSONL = os.path.join(OUT_DIR, "stuck.jsonl")
OUT_MD = os.path.join(OUT_DIR, "stuck.md")

# порог только как справка; решение о «завис» — по state/reason/next_step
REFERENCE_DAYS = 7


def _now():
    return time.time()


def _fmt(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else None


def _age_days(ts):
    return None if not ts else round((_now() - ts) / 86400, 1)


def _row(**kw):
    base = {
        "id": None, "type": None, "title": None, "owner": None,
        "state": "unknown", "reason": None, "next_step": None,
        "last_event_ts": None, "days_since": None, "evidence": None,
        "source": None,
    }
    base.update(kw)
    return base


def from_goals():
    rows = []
    for path in [os.path.join(STATE, "goal.json")] + sorted(
            glob.glob(os.path.join(STATE, "goals", "*.json"))):
        if not os.path.exists(path):
            continue
        try:
            d = json.load(open(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ts = None
        for k in ("updated_at", "updated", "ts"):
            if d.get(k):
                try:
                    ts = time.mktime(time.strptime(str(d[k])[:19], "%Y-%m-%dT%H:%M:%S"))
                except ValueError:
                    pass
                break
        state = d.get("status") or "unknown"
        reason = "цель активна, evidence не зафиксировано" if state == "active" and not d.get("evidence") else None
        next_step = "запросить evidence или закрыть" if reason else None
        rows.append(_row(
            id=f"goal:{os.path.basename(path)}", type="goal",
            title=d.get("objective"), owner=os.path.basename(path).split("-")[0],
            state=state, reason=reason, next_step=next_step,
            last_event_ts=_fmt(ts), days_since=_age_days(ts),
            evidence=d.get("evidence"), source=path.replace(HOME, "~"),
        ))
    return rows


def from_waits():
    rows = []
    if not os.path.exists(WAITS):
        return rows
    for line in open(WAITS, encoding="utf-8"):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = d.get("since_ts")
        ttl = d.get("ttl_minutes")
        if ttl is None and d.get("ttl_hours") is not None:
            ttl = int(d["ttl_hours"]) * 60
        age_min = ((_now() - ts) / 60.0) if ts else None
        overdue = ttl is not None and age_min is not None and age_min > ttl
        rows.append(_row(
            id=f"wait:{d.get('id')}", type="wait", title=d.get("what"),
            owner=d.get("who_owes"), state="waiting",
            reason=(f"ожидание {age_min:.0f}м > TTL {ttl}м" if overdue
                    else f"ожидание {age_min:.0f}м" if age_min is not None else "ожидание"),
            next_step="пинок/закрыть" if overdue else "дождаться или пинок",
            last_event_ts=_fmt(ts), days_since=_age_days(ts),
            evidence=d.get("ref"), source="~/.local/share/ship-mail/waits.jsonl",
        ))
    return rows


def from_letters():
    rows = []
    for path in glob.glob(os.path.join(MAIL, "inbox", "*", "*.md")):
        try:
            ts = os.path.getmtime(path)
        except OSError:
            continue
        rows.append(_row(
            id=f"letter:{os.path.basename(path)}", type="letter",
            title="входящее письмо", state="event",
            reason="событие жизни", next_step="обработать/ack",
            last_event_ts=_fmt(ts), days_since=_age_days(ts),
            source=path.replace(HOME, "~"),
        ))
    return rows


def from_commits(repo, limit=20):
    rows = []
    try:
        out = subprocess.run(
            ["git", "-C", repo, "log", f"-{limit}", "--format=%H|%ct|%s"],
            capture_output=True, text=True, check=False,
        ).stdout
    except OSError:
        return rows
    for line in out.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        sha, ct, subj = parts
        ts = int(ct)
        rows.append(_row(
            id=f"commit:{sha[:8]}", type="commit", title=subj,
            state="event", reason="событие жизни", next_step="—",
            last_event_ts=_fmt(ts), days_since=_age_days(ts),
            source=f"{repo.replace(HOME, '~')}@{sha[:8]}",
        ))
    return rows


def collect():
    return from_goals() + from_waits() + from_commits(DOT)


def build(dry_run=False):
    rows = collect()
    by_type = {}
    for r in rows:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    flagged = [r for r in rows
               if r.get("type") in ("goal", "wait") and r.get("next_step")]
    if dry_run:
        print(f"STUCK dry-run rows={len(rows)} by_type={by_type} flagged={len(flagged)}")
        for r in flagged[:20]:
            print(f"- [{r['type']}] {str(r['title'])[:70]} — {r['reason']} -> {r['next_step']}")
        return 0
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSONL, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("# Тихие зависания (каркас, проекция)\n\n")
        f.write(f"собрано: {time.strftime('%Y-%m-%d %H:%M')} · событий: {len(rows)}\n\n")
        f.write("## Состав\n\n")
        for t, c in sorted(by_type.items()):
            f.write(f"- {t}: {c}\n")
        f.write(f"\n## Кандидаты ({len(flagged)})\n\n")
        for r in flagged:
            f.write(f"- [{r['type']}] {str(r['title'])[:70]} — {r['reason']} -> {r['next_step']}\n")
    print(f"STUCK rows={len(rows)} by_type={by_type} flagged={len(flagged)}")
    print(f"-> {OUT_JSONL}")
    print(f"-> {OUT_MD}")
    return 0


def show():
    if not os.path.exists(OUT_MD):
        print("нет сборки — запусти: stuck.py build")
        return 1
    print(open(OUT_MD, encoding="utf-8").read())
    return 0


def main():
    ap = argparse.ArgumentParser(description="stuck: детектор тихо зависших (каркас)")
    ap.add_argument("cmd", nargs="?", default="build", choices=["build", "show"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.cmd == "show":
        return show()
    return build(dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
