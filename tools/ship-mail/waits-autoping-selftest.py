#!/usr/bin/env python3
"""Selftest шага авто-пинга просроченных ожиданий (waits.py autoping).

Спека: ic-waits-in-wake-cycle-20261107 — просроченная строка реестра ожиданий
сама пингует адресата письмом из цикла пробуждений. Механизм, не дисциплина.

Проверяются три обязательных свойства на изолированном HOME (никаких писем
наружу: транспорт подменяется фейковым ship-mail.sh, который только пишет
строку в свой журнал):

  1) НЕ просроченная строка -> писем нет;
  2) просроченная строка -> РОВНО одно письмо адресату, TTL удвоился
     (backoff Р-075, ping_count +1);
  3) повторный прогон в том же цикле ТТЛ -> нового письма нет (кулдаун).

Плюс отказ: адресат не-sid (owner) не получает письма даже когда просрочен.

Запуск: python3 tools/ship-mail/waits-autoping-selftest.py
Код возврата 0 — всё прошло, 1 — есть провал.
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

FAKE_SHIP_MAIL = """#!/bin/bash
# фейк транспорта: фиксируем факт вызова, писем никуда не шлём
printf '%s\\n' "$*" >> "${FAKE_SEND_LOG}"
exit 0
"""

pass_count = 0
fail_count = 0


def check(label, ok, detail=""):
    global pass_count, fail_count
    if ok:
        print(f"  PASS: {label}")
        pass_count += 1
    else:
        print(f"  FAIL: {label}")
        if detail:
            print(f"        {detail}")
        fail_count += 1


def make_home():
    home = tempfile.mkdtemp(prefix="autoping-", dir="/tmp/opencode")
    os.makedirs(os.path.join(home, "inbox"), exist_ok=True)
    return home


def write_waits(home, rows):
    path = os.path.join(home, "waits.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


def read_rows(home):
    path = os.path.join(home, "waits.jsonl")
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def run_autoping(home, fake_cmd, log_path, extra=(), self_sid=None):
    env = dict(os.environ)
    env["SHIP_MAIL_HOME"] = home
    if self_sid:
        env["SHIP_MAIL_SELF_SID"] = self_sid
    env["SHIP_MAIL_CMD"] = fake_cmd
    env["FAKE_SEND_LOG"] = log_path
    return subprocess.run(
        [sys.executable, WAITS_PY, "autoping", *extra],
        capture_output=True, text=True, env=env, timeout=120)


def sent_lines(log_path):
    if not os.path.exists(log_path):
        return []
    with open(log_path, encoding="utf-8") as f:
        return [ln for ln in f.read().splitlines() if ln.strip()]


# ---------------------------------------------------------------- сценарий 1
print("=== 1) не просроченная строка -> письма нет ===")
home = make_home()
log = os.path.join(home, "send.log")
write_waits(home, [{
    "id": "aaa00001",
    "who_waits": "ses_SENDER01",
    "who_owes": "ses_OWENER01",
    "what": "свежая строка",
    "type": "mandate",
    "state": "open",
    "since_ts": int(time.time()),
    "ttl_minutes": 15,
}])
res = run_autoping(home, os.path.join(home, "fake.sh"), log)
check("нет писем по свежей строке", sent_lines(log) == [], f"sent={sent_lines(log)}")
check("сводка говорит: пинг 0", "пинг 0" in res.stdout, res.stdout.strip())


# ---------------------------------------------------------------- сценарий 2
print("=== 2) просроченная строка -> одно письмо, TTL удвоился ===")
home = make_home()
log = os.path.join(home, "send.log")
fake = os.path.join(home, "fake.sh")
with open(fake, "w", encoding="utf-8") as f:
    f.write(FAKE_SHIP_MAIL)
os.chmod(fake, 0o755)

# адресат не в фикстурном реестре — транспорт фейковый, адресация не проверяется
write_waits(home, [{
    "id": "aaa00002",
    "who_waits": "ses_SENDER01",
    "who_owes": "ses_OWENER02",
    "what": "просроченная строка",
    "type": "mandate",
    "state": "open",
    "since_ts": int(time.time()) - 60 * 60,
    "ttl_minutes": 15,
}])
res = run_autoping(home, fake, log)
sent = sent_lines(log)
check("ровно одно письмо", len(sent) == 1, f"sent={sent}")
if sent:
    check("письмо адресовано who_owes", "--to ses_OWENER02" in sent[0], sent[0])
    check("письмо от who_waits", "--from ses_SENDER01" in sent[0], sent[0])
    check("ref помечен авто-пингом", "--ref waits-autoping-aaa00002" in sent[0], sent[0])
row = read_rows(home)[0]
check("TTL удвоился 15 -> 30", row.get("ttl_minutes") == 30, f"ttl={row.get('ttl_minutes')}")
check("ping_count = 1", row.get("ping_count") == 1, f"ping_count={row.get('ping_count')}")
check("pinged проставлен", bool(row.get("pinged")), f"pinged={row.get('pinged')}")


# ---------------------------------------------------------------- сценарий 3
print("=== 3) повтор в том же цикле ТТЛ -> нового письма нет ===")
res2 = run_autoping(home, fake, log)
sent_after = sent_lines(log)
check("второго письма нет", len(sent_after) == 1, f"всего писем {len(sent_after)}")
check("TTL не вырос вторым прогоном", read_rows(home)[0].get("ttl_minutes") == 30,
      f"ttl={read_rows(home)[0].get('ttl_minutes')}")


# ---------------------------------------------------------------- сценарий 4
print("=== 4) адресат не сессия (owner) -> письмо не шлётся ===")
home = make_home()
log = os.path.join(home, "send.log")
fake = os.path.join(home, "fake.sh")
with open(fake, "w", encoding="utf-8") as f:
    f.write(FAKE_SHIP_MAIL)
os.chmod(fake, 0o755)
write_waits(home, [{
    "id": "aaa00003",
    "who_waits": "ses_SENDER01",
    "who_owes": "owner",
    "what": "вопрос владельцу",
    "type": "question",
    "state": "open",
    "since_ts": int(time.time()) - 60 * 60,
    "ttl_minutes": 15,
}])
res = run_autoping(home, fake, log)
check("владельцу авто-письмо не ушло", sent_lines(log) == [], f"sent={sent_lines(log)}")
check("строка в SKIP", "SKIP aaa00003" in res.stdout, res.stdout.strip())

# ---------------------------------------------------------------- сценарий 5
print("=== 5) ждём от своей же линии -> письмо не шлётся (нет подмены отправителя) ===")
home = make_home()
log = os.path.join(home, "send.log")
fake = os.path.join(home, "fake.sh")
with open(fake, "w", encoding="utf-8") as f:
    f.write(FAKE_SHIP_MAIL)
os.chmod(fake, 0o755)
write_waits(home, [{
    "id": "aaa00005",
    "who_waits": "ses_SENDER01",
    "who_owes": "ses_MESELF01",
    "what": "моя собственная работа",
    "type": "mandate",
    "state": "open",
    "since_ts": int(time.time()) - 60 * 60,
    "ttl_minutes": 15,
}])
res = run_autoping(home, fake, log, self_sid="ses_MESELF01")
check("самому себе письма нет", sent_lines(log) == [], f"sent={sent_lines(log)}")
check("строка помечена SELF", "SELF aaa00005" in res.stdout, res.stdout.strip())
check("TTL не удвоен (работа не сделана)", read_rows(home)[0].get("ttl_minutes") == 15,
      f"ttl={read_rows(home)[0].get('ttl_minutes')}")

print(f"=== {pass_count} pass, {fail_count} fail ===")
sys.exit(0 if fail_count == 0 else 1)
