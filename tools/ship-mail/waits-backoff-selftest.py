#!/usr/bin/env python3
"""Selftest backoff/эскалации пинков (дефект флуда 11.11: 100 писем).

Воспроизведённый дефект: строка с deadline_minutes == ttl_minutes (так их
создаёт `ship-mail.sh send --task`: ttl=deadline_min, deadline=2*deadline_min)
навсегда застревала на TTL: min(old*2, deadline) == old. Пинг повторялся
каждые TTL минут без роста -> 673 письма на строку (интервалы ровно 30.0м).

Проверяется:
  1) TTL удваивается на каждую серию пинков и не застревает равным старту;
  2) при достижении дедлайна строка помечается escalated (человеку), а не
     продолжает пинговаться;
  3) эскалированную строку cmd_autoping больше НЕ пингует (письма прекращаются);
  4) TTL ограничен MAX_TTL_MINUTES (сутки) — нет бесконечного роста.

Изоляция: временный SHIP_MAIL_HOME, фейковый SHIP_MAIL_CMD. Реальные письма
не уходят.
Запуск: python3 tools/ship-mail/waits-backoff-selftest.py
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

FAKE = """#!/bin/bash
echo "$*" >> "${FAKE_SEND_LOG}"
exit 0
"""

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


def fresh_home():
    home = tempfile.mkdtemp(prefix="backoff-", dir="/tmp/opencode")
    os.makedirs(os.path.join(home, "inbox"), exist_ok=True)
    fake = os.path.join(home, "fake.sh")
    with open(fake, "w", encoding="utf-8") as f:
        f.write(FAKE)
    os.chmod(fake, 0o755)
    return home, fake, os.path.join(home, "send.log")


def env_for(home, fake):
    env = dict(os.environ)
    env["SHIP_MAIL_HOME"] = home
    env["SHIP_MAIL_CMD"] = fake
    env["FAKE_SEND_LOG"] = os.path.join(home, "send.log")
    env.pop("OPENCODE_SESSION_ID", None)
    env.pop("SHIP_MAIL_SELF_SID", None)
    return env


def run(env, *args):
    return subprocess.run([sys.executable, WAITS_PY, *args],
                          capture_output=True, text=True, env=env, timeout=60)


def rows(home):
    p = os.path.join(home, "waits.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def write_row(home, row):
    p = os.path.join(home, "waits.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def pings_sent(log):
    if not os.path.exists(log):
        return 0
    with open(log, encoding="utf-8") as f:
        return sum(1 for ln in f if ln.strip())


# ------------------------------------------------ 1) backoff не застревает
print("=== 1) TTL растёт, не застревает на deadline ==")
home, fake, log = fresh_home()
env = env_for(home, fake)
write_row(home, {
    "id": "tst00001", "who_waits": "ses_OTHER01", "who_owes": "ses_OTHER02",
    "what": "ждём исполнения", "ref": "r1", "type": "mandate", "state": "open",
    "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "since_ts": int(time.time()) - 600,
    "ttl_minutes": 30, "deadline_minutes": 30,
})
ttls = []
for _ in range(4):
    out = run(env, "ping", "tst00001")
    ttls.append(rows(home)[0]["ttl_minutes"])
check("TTL строго растёт (был заклинен на 30)", ttls == sorted(ttls) and ttls[0] < ttls[-1],
      f"ttls={ttls}")
check("не застревает равным старту", len(set(ttls)) > 1, f"ttls={ttls}")


# ------------------------------------------------ 2) эскалация при дедлайне
print("=== 2) дедлайн исчерпан -> escalated, письма прекращаются ===")
home, fake, log = fresh_home()
env = env_for(home, fake)
write_row(home, {
    "id": "tst00002", "who_waits": "ses_OTHER01", "who_owes": "ses_OTHER03",
    "what": "ждём исполнения", "ref": "r2", "type": "mandate", "state": "open",
    "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    # возраст 40м > дедлайн 30м: дедлайн это срок ОТ ОТКРЫТИЯ, не порог TTL
    "since_ts": int(time.time()) - 40 * 60,
    "ttl_minutes": 30, "deadline_minutes": 30,
})
r0 = run(env, "ping", "tst00002")
row = rows(home)[0]
check("строка помечена escalated", bool(row.get("escalated")), json.dumps(row, ensure_ascii=False))
check("print говорит ЭСКАЛАЦИЯ", "ЭСКАЛАЦИЯ" in r0.stdout, r0.stdout.strip())

# Состариваем строку заведомо за TTL, СОХРАНЯЯ метку escalated:
# проверяем именно «эскалированную не пингуем», а не «не просрочена».
stale = rows(home)[0]
stale["since_ts"] = int(time.time()) - 100000
write_row(home, stale)

n0 = pings_sent(log)
out = run(env, "autoping")
n1 = pings_sent(log)
check("авто-пинг не шлёт по эскалированной строке", n1 == n0,
      f"до={n0}, после={n1}")
check("в выводе SKIP с причиной «эскалирована»", "эскалирована" in out.stdout
      or "прекращены" in out.stdout, out.stdout.strip())


# ------------------------------------------------ 3) потолок TTL
print("=== 3) TTL не растёт выше суток ===")
home, fake, log = fresh_home()
env = env_for(home, fake)
write_row(home, {
    "id": "tst00003", "who_waits": "ses_OTHER01", "who_owes": "ses_OTHER04",
    "what": "долгое ожидание", "ref": "r3", "type": "mandate", "state": "open",
    "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "since_ts": int(time.time()) - 600, "ttl_minutes": 30,
})
for _ in range(12):
    run(env, "ping", "tst00003")
ttl_max = rows(home)[0]["ttl_minutes"]
check("потолок 1440 минут соблюдён", ttl_max <= 1440, f"ttl={ttl_max}")

# ------------------------------------------------ 4) свежее задание не эскалируется рано
print("=== 4) задание send --task (ttl=15/dl=30) не эскалируется на первом пинке ===")
home, fake, log = fresh_home()
env = env_for(home, fake)
write_row(home, {
    "id": "tst00004", "who_waits": "ses_OTHER01", "who_owes": "ses_OTHER05",
    "what": "задание: письмо с исполнением", "ref": "r4", "type": "mandate",
    "state": "open",
    "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "since_ts": int(time.time()) - 16 * 60,   # 16м: за TTL 15, но до дедлайна 30
    "ttl_minutes": 15, "deadline_minutes": 30,
})
out = run(env, "ping", "tst00004")
row = rows(home)[0]
check("нет эскалации до дедлайна", not row.get("escalated"), json.dumps(row, ensure_ascii=False))
check("TTL вырос 15 -> 30", row.get("ttl_minutes") == 30, f"ttl={row.get('ttl_minutes')}")

print(f"=== {passed} pass, {failed} fail ===")
sys.exit(0 if failed == 0 else 1)
