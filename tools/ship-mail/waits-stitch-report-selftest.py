#!/usr/bin/env python3
"""Selftest отчёта «ответ без пришивки» (дефект BF-20261119-02).

Дефект, найденный живьём 19.11: `waits.py stitch-report` отбирал строки
ИНВЕРТИРОВАННО — показывал строки, пришитые штатно (op=stitch, state=answered),
и молчал о строках, закрытых через `done` БЕЗ пришивки. На живых данных это
дало ложные «ОТВЕТ БЕЗ ПРИШИВКИ» на здоровых строках (f0f0ab51) и ноль
сигнала по реально непришитым (f0d4c8e8, f0ed90f4) — отчёт показывал ровно
не то, что должен.

Проверяется:
  1) закрытая без пришивки строка с ответом в ящике → в отчёте, с подсказкой
     штатного восстановления (stitch --recover);
  2) строка, пришитая штатно (op=stitch) → в отчёте НЕ появляется (главная
     регрессия дефекта);
  3) строка, восстановленная (op=stitch-recovery) → тоже НЕ появляется;
  4) закрытая без пришивки строка старше окна 24ч → в подробности не попадает,
     считается в «СТАРЫЕ БЕЗ ПРИШИВКИ»;
  5) закрытая без пришивки строка, ответа в ящике нет → в отчёте с честной
     пометкой «ответ не найден»;
  6) `done` при уже пришедшем ответе → печатает ВНИМАНИЕ с командой починки.

Изоляция: временный SHIP_MAIL_HOME.
Запуск: python3 tools/ship-mail/waits-stitch-report-selftest.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WAITS_PY = os.path.join(HERE, "waits.py")

passed = 0
failed = 0


def check(label, ok, detail=""):
    global passed, failed
    if ok:
        print(f"  PASS: {label}")
        passed += 1
    else:
        print(f"  FAIL: {label}")
        if detail:
            print(f"        {detail}")
        failed += 1


def make_home():
    home = tempfile.mkdtemp(prefix="stitch-report-", dir="/tmp/opencode")
    os.makedirs(os.path.join(home, "inbox"), exist_ok=True)
    env = dict(os.environ)
    env["SHIP_MAIL_HOME"] = home
    env.pop("OPENCODE_SESSION_ID", None)
    return home, env


def run(env, *args):
    return subprocess.run([sys.executable, WAITS_PY, *args],
                          capture_output=True, text=True, env=env, timeout=60)


def rows(home, name):
    p = os.path.join(home, name)
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def seed_wait(home, wid, since_ts, closed_ts=None, who_waits="ses_WAIT01",
              who_owes="ses_OWED01", what="приёмка коммитов"):
    row = {
        "id": wid,
        "who_waits": who_waits,
        "who_owes": who_owes,
        "what": what,
        "ref": f"ref-{wid}",
        "type": "acceptance",
        "state": "closed",
        "return_condition": "письмо с вердиктом",
        "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(since_ts)),
        "since_ts": since_ts,
        "ttl_minutes": 120,
    }
    if closed_ts is not None:
        row["closed"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(closed_ts))
    with open(os.path.join(home, "waits-done.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def seed_letter(home, waiter, sender, ts, name="letter.md"):
    d = os.path.join(home, "inbox", waiter)
    os.makedirs(d, exist_ok=True)
    iso = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(ts))
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        f.write(f"---\ntype: Letter\nfrom: {sender}\nto: {waiter}\n"
                f"title: \"ответ\"\nref: \"answer-{name}\"\nts: {iso}\n---\n\n"
                f"Ответ по существу.\n")
    return name


now = int(time.time())
hour = 3600

print("=== 1) закрытая без пришивки строка с ответом → в отчёте ===")
home, env = make_home()
seed_wait(home, "rep00001", since_ts=now - 5 * hour, closed_ts=now - 2 * hour)
seed_letter(home, "ses_WAIT01", "ses_OWED01", now - 3 * hour)
r = run(env, "stitch-report")
check("rc=0", r.returncode == 0, f"rc={r.returncode}, out={r.stdout}, err={r.stderr}")
check("строка rep00001 в отчёте", "rep00001" in r.stdout, r.stdout.strip())
check("пометка «ответ найден»", "ответ найден" in r.stdout, r.stdout.strip())
check("есть команда починки stitch --recover",
      "--recover" in r.stdout and "authorized-by" in r.stdout, r.stdout.strip())
check("счётчик STITCH-REPORT 1", "STITCH-REPORT 1" in r.stdout, r.stdout.strip())

print("=== 2) строка, пришитая штатно → в отчёте НЕ появляется ===")
home, env = make_home()
seed_wait(home, "rep00002", since_ts=now - 5 * hour, closed_ts=now - 2 * hour)
seed_letter(home, "ses_WAIT01", "ses_OWED01", now - 3 * hour)
stitched = {
    "id": "rep00002", "who_waits": "ses_WAIT01", "who_owes": "ses_OWED01",
    "what": "приёмка коммитов", "type": "acceptance", "state": "answered",
    "since_ts": now - 5 * hour, "op": "stitch",
    "reply_to": "letter.md", "answered_by": "ses_OWED01",
    "answered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 3 * hour)),
    "stitched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 3 * hour)),
    "lag_minutes": 120, "op_deadline_minutes": 24 * 60,
}
with open(os.path.join(home, "waits-done.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps(stitched, ensure_ascii=False) + "\n")
r = run(env, "stitch-report")
check("rc=0", r.returncode == 0, f"rc={r.returncode}, out={r.stdout}")
check("rep00002 НЕ показан", "rep00002" not in r.stdout, r.stdout.strip())
check("STITCH-REPORT 0", "STITCH-REPORT 0" in r.stdout, r.stdout.strip())

print("=== 3) восстановленная строка (stitch-recovery) → НЕ показывается ===")
home, env = make_home()
seed_wait(home, "rep00003", since_ts=now - 5 * hour, closed_ts=now - 2 * hour)
seed_letter(home, "ses_WAIT01", "ses_OWED01", now - 3 * hour)
rec = dict(seed_wait(home, "rep00003", since_ts=now - 5 * hour,
                     closed_ts=now - 2 * hour))
rec.update({"op": "stitch-recovery", "state": "answered", "recovery": True,
            "answered_by": "ses_OWED01",
            "answered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 3 * hour)),
            "stitched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 3 * hour))})
with open(os.path.join(home, "waits-done.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
r = run(env, "stitch-report")
check("rc=0", r.returncode == 0, f"rc={r.returncode}, out={r.stdout}")
check("rep00003 НЕ показан", "rep00003" not in r.stdout, r.stdout.strip())
check("STITCH-REPORT 0", "STITCH-REPORT 0" in r.stdout, r.stdout.strip())

print("=== 4) старая строка (>24ч) → в подробности не попадает, считается ===")
home, env = make_home()
seed_wait(home, "rep00004", since_ts=now - 72 * hour, closed_ts=now - 48 * hour)
seed_letter(home, "ses_WAIT01", "ses_OWED01", now - 50 * hour)
r = run(env, "stitch-report")
check("rc=0", r.returncode == 0, f"rc={r.returncode}, out={r.stdout}")
check("rep00004 НЕ в подробностях", "rep00004" not in r.stdout.split("СТАРЫЕ")[0],
      r.stdout.strip())
check("есть сводка СТАРЫЕ БЕЗ ПРИШИВКИ", "СТАРЫЕ БЕЗ ПРИШИВКИ" in r.stdout,
      r.stdout.strip())
check("STITCH-REPORT 0", "STITCH-REPORT 0" in r.stdout, r.stdout.strip())

print("=== 5) закрытая без пришивки, ответа в ящике нет → честная пометка ===")
home, env = make_home()
seed_wait(home, "rep00005", since_ts=now - 5 * hour, closed_ts=now - 2 * hour)
r = run(env, "stitch-report")
check("rc=0", r.returncode == 0, f"rc={r.returncode}, out={r.stdout}")
check("rep00005 показан", "rep00005" in r.stdout, r.stdout.strip())
check("пометка «ответ не найден»", "ответ не найден" in r.stdout, r.stdout.strip())

print("=== 6) done при уже пришедшем ответе → ВНИМАНИЕ с починкой ===")
home, env = make_home()
row = {
    "id": "rep00006", "who_waits": "ses_WAIT01", "who_owes": "ses_OWED01",
    "what": "приёмка коммитов", "ref": "ref-rep00006", "type": "acceptance",
    "state": "open", "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - hour)),
    "since_ts": now - hour, "ttl_minutes": 120,
}
with open(os.path.join(home, "waits.jsonl"), "w", encoding="utf-8") as f:
    f.write(json.dumps(row, ensure_ascii=False) + "\n")
seed_letter(home, "ses_WAIT01", "ses_OWED01", now - 1800)
r = run(env, "done", "rep00006")
check("rc=0", r.returncode == 0, f"rc={r.returncode}, out={r.stdout}, err={r.stderr}")
check("DONE напечатан", "DONE rep00006" in r.stdout, r.stdout.strip())
check("есть ВНИМАНИЕ про ответ без пришивки", "БЕЗ пришивки" in r.stdout, r.stdout.strip())
check("есть команда stitch --recover", "--recover" in r.stdout, r.stdout.strip())

print("=== 7) пометка op=close-note — не закрытие, в отчёт не идёт ===")
home, env = make_home()
note = {"op": "close-note", "id": "rep00007", "state": "closed",
        "note": "контроль: срок истёк, маршрут исполнен",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - hour))}
with open(os.path.join(home, "waits-done.jsonl"), "w", encoding="utf-8") as f:
    f.write(json.dumps(note, ensure_ascii=False) + "\n")
r = run(env, "stitch-report")
check("rc=0", r.returncode == 0, f"rc={r.returncode}, out={r.stdout}")
check("rep00007 НЕ показан", "rep00007" not in r.stdout, r.stdout.strip())
check("STITCH-REPORT 0", "STITCH-REPORT 0" in r.stdout, r.stdout.strip())

print(f"=== {passed} pass, {failed} fail ===")
sys.exit(0 if failed == 0 else 1)
