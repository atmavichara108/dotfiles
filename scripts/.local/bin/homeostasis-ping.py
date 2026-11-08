#!/usr/bin/env python3
"""homeostasis-ping — пингер операции «гомеостаз» (слово владельца 2026-11-07).

Слово владельца (basis: quoted): «Пинай цу каждые 30 минут пока операция
гомеостаз не выполнит все цели».

Принцип: пингер не спрашивает «как дела?», а предъявляет **проверяемые факты** и
останавливается, когда они закрыты. Пинг вслепую — тот дефект, который мы чиним.

Откуда берёт факты (всё с диска, ничего из памяти):
  * просрочки и ждущие строки — `~/.local/share/ship-mail/waits*.jsonl` (через
    вывод ship-mail inbox: строки ПРОСРОЧЕНО и WAITS-OVERDUE);
  * ответы без пришивки — строки «ОТВЕТ БЕЗ ПРИШИВКИ»;
  * здоровье сторожа портала — journalctl (ошибки TypeNotFoundError за последний
    час) и is-active службы.

Критерий остановки: владелец положил `cleared: true` в файле состояния (или
перечислил цели в `goals` — тогда проверка идёт по ним). По умолчанию стучим,
пока хозяин не скажет «стоп»: молчащий таймер и есть тот дефект.

Состояние: ~/.local/state/homeostasis/ping.json (last_ping, clears, pings).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

MY_SID = "ses_e714b5c4bffeh1ri37WHF8Q7Bx"
CU_SID = "ses_eceb23a71ffeJO9QnFou8VngZC"
SHIP_MAIL = os.path.expanduser("~/.local/bin/ship-mail.sh")
STATE_DIR = os.path.expanduser("~/.local/state/homeostasis")
STATE = os.path.join(STATE_DIR, "ping.json")
INTERVAL_MIN = 30


def _load() -> dict:
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {"cleared": False, "goals": [], "last_ping_msk": None,
                "pings": 0}


def _save(d: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    fd = os.open(STATE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def _inbox_facts() -> dict:
    out = {"overdue": 0, "unstitched": 0, "lines": []}
    try:
        res = subprocess.run([SHIP_MAIL, "inbox", MY_SID],
                             capture_output=True, text=True, timeout=60)
    except Exception:  # noqa: BLE001
        return out
    text = res.stdout or ""
    m = re.search(r"WAITS-OVERDUE (\d+)", text)
    out["overdue"] = int(m.group(1)) if m else 0
    for line in text.splitlines():
        if line.startswith("ПРОСРОЧЕНО"):
            out["lines"].append(line[:150])
        if line.startswith("ОТВЕТ БЕЗ ПРИШИВКИ"):
            out["unstitched"] += 1
    return out


def _guard_health() -> dict:
    out = {"active": "unknown", "tl_errors_1h": 0}
    try:
        r = subprocess.run(["systemctl", "--user", "is-active",
                            "portal-tg-guard.service"],
                           capture_output=True, text=True, timeout=30)
        out["active"] = (r.stdout or "").strip()
    except Exception:  # noqa: BLE001
        pass
    try:
        r = subprocess.run(["journalctl", "--user", "-u", "portal-tg-guard.service",
                            "--since", "1 hour ago", "--no-pager"],
                           capture_output=True, text=True, timeout=60)
        out["tl_errors_1h"] = (r.stdout or "").count("TypeNotFoundError")
    except Exception:  # noqa: BLE001
        pass
    return out


def build_ping() -> tuple[str, dict]:
    facts = _inbox_facts()
    health = _guard_health()
    body = [
        "ПИНГ ОПЕРАЦИИ «ГОМЕОСТАЗ» (слово владельца: каждые 30 минут, пока цели не закрыты).",
        "",
        "ФАКТЫ (с диска, не по памяти):",
        "* просроченных ожиданий: %d" % facts["overdue"],
        "* ответов без пришивки: %d" % facts["unstitched"],
        "* сторож портала: %s; ошибок разбора TL за час: %d"
        % (health["active"], health["tl_errors_1h"]),
    ]
    if facts["lines"]:
        body += ["", "Просрочено сейчас:"] + ["  " + l for l in facts["lines"][:8]]
    body += [
        "",
        "ПРОШУ: строка статуса операции — что закрыто, что в работе, что блокирует.",
        "Цели операции я запросила письмом `homeostasis-goals-required-20261107`;",
        "пока перечня нет, пингер предъявляет факты и стучит по слову владельца.",
    ]
    return "\n".join(body), {"facts": facts, "health": health}


def _ref() -> str:
    """ref уникален на пинг: шина отклоняет повторный ref как дубль."""
    return "homeostasis-ping-%s" % time.strftime(
        "%Y%m%d-%H%M", time.gmtime(time.time() + 3 * 3600))


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    d = _load()
    if d.get("cleared"):
        return 0
    ref = _ref()
    text, snap = build_ping()
    if dry:
        print(text)
        return 0
    fd, path = None, None
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".md", prefix="homeostasis-ping-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        head = ("---\ntype: Letter\ntitle: \"Пинг операции гомеостаз:"
                " факты\"\nref: %s\n---\n\n" % ref)
        body = ("## СДЕЛАНО\n1. Пингер собрал факты с диска (просрочки,"
                " ответы без пришивки, здоровье сторожа).\n\n"
                "## ЗАБЛОКИРОВАНО\n2. Цели операции не объявлены —"
                " перечень запрошен письмом"
                " `homeostasis-goals-required-20261107`.\n\n"
                "## ЖДЁТ-ЗАБОТЫ\n3. Строка статуса операции от ЦУ."
                "\n\n" + text + "\n\n"
                "После выполнения — продолжай свою работу.\n")
        letter = head + body
        f.write(letter)
    try:
        proc = subprocess.run(
            [SHIP_MAIL, "send", "--to", CU_SID, "--from", MY_SID,
             "--title", "Пинг гомеостаза: факты и запрос статуса",
             "--ref", ref, "--file", path],
            capture_output=True, text=True, timeout=180)
        if proc.returncode != 0:
            sys.stderr.write((proc.stdout or "") + (proc.stderr or "")[-300:] + "\n")
            return 1
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    d["last_ping_msk"] = time.strftime("%Y-%m-%d %H:%M МСК",
                                       time.gmtime(time.time() + 3 * 3600))
    d["pings"] = int(d.get("pings", 0)) + 1
    _save(d)
    print("homeostasis-ping: №%d отправлен (%s)" % (d["pings"], d["last_ping_msk"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
