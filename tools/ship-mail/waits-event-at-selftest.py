#!/usr/bin/env python3
"""Selftest «двух времён строки» (аудит Школы 2026-11-07, sha 9ccec4db41f5a500).

Дефект дня 08.11: строка слота с событием «подтверждение старта к 10:15»
печаталась как «просрочено», хотя срок был по ШКАЛЕ события, а не молчание
адресата: since+ttl считал возраст от первой даты. Правило: у строки два
времени — since (создана) и event_at (когда событие свершается); до события
строка event-pending и НЕ пингуется (доминирует над TTL), после — по шкале.

Проверяется:
  1) будущее событие в what -> не просрочено, вид event-pending;
  2) явное поле event_at (ISO) работает и важнее парсинга;
  3) прошедшая дата в тексте НЕ делает строку event-pending (это факт, не план);
  4) после наступления события строка снова считается по шкале (просрочена);
  5) tz у event_at — MSK (+03), а не «по машине»: epoch сдвинут на 3 часа.

Запуск: python3 tools/ship-mail/waits-event-at-selftest.py
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


def home_env():
    home = tempfile.mkdtemp(prefix="event-at-", dir="/tmp/opencode")
    os.makedirs(os.path.join(home, "inbox"), exist_ok=True)
    env = dict(os.environ)
    env["SHIP_MAIL_HOME"] = home
    env.pop("OPENCODE_SESSION_ID", None)
    return home, env


def write_rows(home, rows):
    with open(os.path.join(home, "waits.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def base_row(wid, **kw):
    now = int(time.time())
    row = {
        "id": wid, "who_waits": "ses_W01", "who_owes": "ses_O01",
        "what": "строка", "ref": "r-" + wid, "type": "mandate", "state": "open",
        "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 7200)),
        "since_ts": now - 7200,     # возраст 2ч, TTL ниже => по шкале просрочено
        "ttl_minutes": 30,
    }
    row.update(kw)
    return row


def run(env, *args):
    return subprocess.run([sys.executable, WAITS_PY, *args],
                          capture_output=True, text=True, env=env, timeout=60)


print("=== 1) будущее событие в what -> event-pending, не просрочено ===")
home, env = home_env()
future = time.localtime(time.time() + 2 * 3600)
stamp = time.strftime("%d.%m %H:%M", future)
write_rows(home, [base_row("ev000001", what=f"слот интеграции, подтверждение к {stamp}")])
out = run(env, "list").stdout
check("вид event-pending", "event-pending" in out, out.strip())
out_od = run(env, "overdue").stdout
check("не попала в overdue", "ev000001" not in out_od, out_od.strip())

print("=== 2) явное поле event_at важнее парсинга ===")
home, env = home_env()
iso_future = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
write_rows(home, [base_row("ev000002", what="без даты в тексте", event_at=iso_future)])
out = run(env, "overdue").stdout
check("явный event_at в будущем -> не просрочено", "ev000002" not in out, out.strip())

print("=== 3) прошедшая дата в тексте не делает строку event-pending ===")
home, env = home_env()
past = time.localtime(time.time() - 5 * 3600)
stamp_past = time.strftime("%d.%m %H:%M", past)
write_rows(home, [base_row("ev000003", what=f"ответ был к {stamp_past}")])
out = run(env, "overdue").stdout
check("прошедшая дата -> строка по шкале (просрочена)", "ev000003" in out, out.strip())

print("=== 4) после наступления события строка снова по шкале ===")
home, env = home_env()
soon = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60))
write_rows(home, [base_row("ev000004", event_at=soon)])
out = run(env, "overdue").stdout
check("event_at в прошлом не спасает от просрочки", "ev000004" in out, out.strip())

print("=== 5) tz события — MSK (+03), а не машинный ===")
home, env = home_env()
# 12:00 MSK = 09:00 UTC. Через поле event_at это должно дать сдвиг ровно +3ч
import datetime as dt
target = (dt.datetime.now(dt.timezone(dt.timedelta(hours=3)))
          + dt.timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
iso_local = target.strftime("%Y-%m-%dT%H:%M:00")
write_rows(home, [base_row("ev000005", event_at=iso_local)])
sys.path.insert(0, HERE)
import importlib.util
spec = importlib.util.spec_from_file_location("waits_mod", WAITS_PY)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
row = json.loads(open(os.path.join(home, "waits.jsonl"), encoding="utf-8").readline())
ts, src = mod._event_at(row)
expect = target.timestamp()
check("epoch совпадает с MSK-смещением", ts is not None and abs(ts - expect) < 1,
      f"ts={ts}, expect={expect}, src={src}")

print(f"=== {passed} pass, {failed} fail ===")
sys.exit(0 if failed == 0 else 1)
