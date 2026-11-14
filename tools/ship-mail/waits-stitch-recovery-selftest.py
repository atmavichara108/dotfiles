#!/usr/bin/env python3
"""Selftest штатного восстановления пришивки (дефект Храма 1173282c815c).

Дефект, найденный живьём: waits.py stitch отказывал строке, закрытой БЕЗ
пришивки ("ожидание уже закрыто"), поэтому восстановительные записи делали
в обход инструмента — отдельной записью под flock, без штатного пути.

Теперь восстановление — штатная операция `stitch --recover`:
  * требует --evidence (чем доказан ответ) и --authorized-by (санкция);
  * пишет append-only op=stitch-recovery с recovery=true;
  * НЕ переписывает прежние записи (журнал остаётся журналом);
  * повтор идемпотентен: «уже пришито».

Проверяется:
  1) закрытая без stitch строка: обычный stitch → rc=3 и подсказка штатного пути;
  2) --recover без evidence/санкции → rc=2, запись НЕ создана;
  3) --recover с evidence+санкцией → op=stitch-recovery, recovery=true, lag посчитан;
  4) прежняя закрытая запись не тронута (append-only);
  5) повторный --recover → «уже пришито», дубля нет.

Изоляция: временный SHIP_MAIL_HOME.
Запуск: python3 tools/ship-mail/waits-stitch-recovery-selftest.py
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
    home = tempfile.mkdtemp(prefix="stitch-rec-", dir="/tmp/opencode")
    os.makedirs(os.path.join(home, "inbox"), exist_ok=True)
    env = dict(os.environ)
    env["SHIP_MAIL_HOME"] = home
    env.pop("OPENCODE_SESSION_ID", None)
    return home, env


def run(env, *args):
    return subprocess.run([sys.executable, WAITS_PY, *args],
                          capture_output=True, text=True, env=env, timeout=60)


def done_rows(home):
    p = os.path.join(home, "waits-done.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def seed_closed_without_stitch(home, wid="rec00001"):
    """Строка закрыта механически: state=closed, op=stitch НЕТ."""
    since_ts = int(time.time()) - 3 * 3600
    row = {
        "id": wid,
        "who_waits": "ses_OWNER01",
        "who_owes": "ses_OWED01",
        "what": "слот интеграции: подтверждение старта",
        "ref": "win-integration-slot",
        "type": "mandate",
        "state": "closed",
        "return_condition": "письмо со стартом",
        "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(since_ts)),
        "since_ts": since_ts,
        "ttl_minutes": 60,
        "closed": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(since_ts + 3600)),
    }
    with open(os.path.join(home, "waits-done.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


print("=== 1) обычный stitch на закрытой строке: отказ с подсказкой ===")
home, env = make_home()
seed_closed_without_stitch(home)
r = run(env, "stitch", "rec00001", "--answered-at", time.strftime(
    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
check("rc=3 (не молчаливый успех)", r.returncode == 3, f"rc={r.returncode}, out={r.stdout}")
check("подсказка содержит --recover и --authorized-by",
      "--recover" in r.stdout and "--authorized-by" in r.stdout, r.stdout.strip())
check("запись пришивки НЕ создана", len(done_rows(home)) == 1, f"строк={len(done_rows(home))}")

print("=== 2) --recover без evidence/санкции: отказ ===")
r = run(env, "stitch", "rec00001", "--recover",
        "--answered-at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
check("rc=2 без evidence и санкции", r.returncode == 2, f"rc={r.returncode}, out={r.stdout}")
check("ничего не дописано", len(done_rows(home)) == 1, f"строк={len(done_rows(home))}")

print("=== 3) --recover с evidence и санкцией: штатное восстановление ===")
answered = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 7200))
r = run(env, "stitch", "rec00001", "--recover",
        "--answered-at", answered,
        "--evidence", "письмо линии окон 08.11: слот принят",
        "--authorized-by", "Храм (76b2ad39c959)")
rows = done_rows(home)
rec = [x for x in rows if x.get("op") == "stitch-recovery"]
check("rc=0", r.returncode == 0, f"rc={r.returncode}, out={r.stdout}")
check("создана ровно одна запись stitch-recovery", len(rec) == 1, f"строк={len(rows)}")
if rec:
    check("recovery=true", rec[0].get("recovery") is True, json.dumps(rec[0], ensure_ascii=False))
    check("санкция сохранена", "76b2ad39c959" in str(rec[0].get("authorized_by")), str(rec[0].get("authorized_by")))
    check("lag посчитан", isinstance(rec[0].get("lag_minutes"), (int, float)), str(rec[0].get("lag_minutes")))
    check("state=answered", rec[0].get("state") == "answered", str(rec[0].get("state")))

print("=== 4) append-only: прежняя закрытая запись не тронута ===")
first = rows[0]
check("первая запись осталась state=closed", first.get("state") == "closed", json.dumps(first, ensure_ascii=False))
check("у первой записи нет op=stitch-recovery",
      first.get("op") != "stitch-recovery", str(first.get("op")))

print("=== 5) повтор --recover идемпотентен ===")
r = run(env, "stitch", "rec00001", "--recover",
        "--answered-at", answered,
        "--evidence", "повтор", "--authorized-by", "Храм")
check("rc=0 (повтор не ошибка)", r.returncode == 0, f"rc={r.returncode}")
check("говорит «уже пришито»", "уже пришито" in r.stdout, r.stdout.strip())
check("дубля не создано", len([x for x in done_rows(home)
                               if x.get("op") == "stitch-recovery"]) == 1,
      f"строк={len(done_rows(home))}")

print(f"=== {passed} pass, {failed} fail ===")
sys.exit(0 if failed == 0 else 1)
