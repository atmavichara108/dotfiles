#!/usr/bin/env python3
"""homeostasis-ping v2 — операция «гомеостаз» после провала (перезапуск 08.11).

Приказ владельца 2026-11-08: «Найти причины провала и запиить операцию заново»
и «Операция гомеостаз запущена?» — ответ: запущена, вот механизм.

Что изменено против версии, которая молчала 9 часов и считала по врщему экрану:
1. Факты берутся из РЕЕСТРА ожиданий (waits.jsonl), не из вывода команды inbox.
2. Возраст самого старого НЕПРОЧИТАННОГО письма считается отдельно: >30 минут —
   это дефект (причина №1 провала: 9 часов непрочитанных ответов).
3. Наблюдатель операции: старт, срок, и статус восьми целей в каждом пинге.
4. Самопроверка: если отправка не удалась — строка в журнал с причиной (таймер больше
   не «сыплет молча»).
5. Цели — канон ЦУ (cu-goals-canon-20261107): адресация, учёт, доказательства,
   канал, сторожа, идемпотентность, устойчивость, ночь без хозяина.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import time

MY_SID = "ses_e714b5c4bffeh1ri37WHF8Q7Bx"
CU_SID = "ses_eceb23a71ffeJO9QnFou8VngZC"
SHIP_MAIL = os.path.expanduser("~/.local/bin/ship-mail.sh")
INBOX = pathlib.Path.home() / ".local/share/ship-mail/inbox" / MY_SID
WAITS_CLI = os.path.expanduser("~/dotfiles/tools/ship-mail/waits.py")
STATE_DIR = os.path.expanduser("~/.local/state/homeostasis")
STATE = os.path.join(STATE_DIR, "ping.json")
MSK = dt.timezone(dt.timedelta(hours=3))

GOALS = [
    ("G1 адресация", "0 получателей вне реестра и 0 строк реестра без агента/каталога/зоны"),
    ("G2 учёт", "0 строк без билета/срока; ответ-без-пришивки = 0"),
    ("G3 доказательства", "100% слов владельца дословно; 0 решений без persist"),
    ("G4 канал", "0 писем без линта; 0 зовов без записи"),
    ("G5 сторожа", "0 повторов; 0 claims вне реестра; 0 неистёкших просроченных"),
    ("G6 идемпотентность", "двойной feed/ack/send без дублей"),
    ("G7 устойчивость", "падение одного таймера не глушит остальные"),
    ("G8 ночь без хозяина", "ночной прогон без вмешательства; вердикт владельца"),
]
UNREAD_LIMIT_MIN = 30


def _now() -> dt.datetime:
    return dt.datetime.now(MSK)


def _fmt(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M МСК")


def _load() -> dict:
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _save(d: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    fd = os.open(STATE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def _waits_facts() -> dict:
    """Факты из реестра — через канонический счётчик waits.py overdue.

    Дефект, который я внесла сама и который поймала ЦУ (задача У-3): свой
    подсчёт по полю ttl_hours — а в реестре поля ttl_minutes и deadline_minutes.
    Поэтому мой экран показывал «просрочено 0», когда канон видел 8. Один
    счётчик на двоих: только waits.py."""
    out = {"open": 0, "overdue": 0, "owed_by_me": 0, "lines": []}
    try:
        r = subprocess.run(["python3", WAITS_CLI, "overdue"],
                           capture_output=True, text=True, timeout=120)
        for line in (r.stdout or "").splitlines():
            if not line.startswith("ПРОСРОЧЕНО"):
                continue
            out["overdue"] += 1
            parts = line.split("|")
            if len(parts) >= 3:
                what = parts[1].strip()
                who = parts[2].replace("ждём от", "").strip()
                if who == MY_SID:
                    out["owed_by_me"] += 1
                out["lines"].append("%s → %s" % (what[:70], who[:20]))
    except Exception:  # noqa: BLE001
        pass
    try:
        r = subprocess.run(["python3", WAITS_CLI, "list"],
                           capture_output=True, text=True, timeout=120)
        # формат waits.py list — строки «id [type/open] …»; считаем по метке
        out["open"] = (r.stdout or "").count("/open]")
    except Exception:  # noqa: BLE001
        pass
    return out


def _unread_facts() -> dict:
    """Непрочитанные — только письма в папках отправителей, НЕ в read/ (архив).

    Дефект, который я внесла сама: первая версия обходила все подкаталоги и
    считала архив прочитанных как непрочитанные — получилось «95 писем, старое
    7.7 суток». Экрана, который врёт, быть не должно (канон A6)."""
    out = {"count": 0, "oldest_min": 0, "archived": 0}
    if not INBOX.is_dir():
        return out
    oldest = None
    for sid in INBOX.iterdir():
        if not sid.is_dir() or sid.name == "read":
            continue
        for f in sid.glob("*.md"):
            out["count"] += 1
            mtime = dt.datetime.fromtimestamp(f.stat().st_mtime, MSK)
            oldest = mtime if oldest is None else min(oldest, mtime)
    archive = INBOX / "read"
    if archive.is_dir():
        out["archived"] = len(list(archive.glob("*.md")))
    if oldest:
        out["oldest_min"] = int((_now() - oldest).total_seconds() // 60)
    return out


def _guard_facts() -> dict:
    out = {"tl_errors_1h": 0, "active": "?"}
    try:
        r = subprocess.run(["systemctl", "--user", "is-active",
                            "portal-tg-guard.service"], capture_output=True,
                           text=True, timeout=30)
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


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    relaunch = "--relaunch" in argv
    d = _load()
    if relaunch:
        start = _now()
        d.update({
            "cleared": False,
            "started_msk": _fmt(start),
            "deadline_msk": _fmt(start + dt.timedelta(hours=8)),
            "pings": 0,
            "last_ping_msk": None,
            "goals": [g[0] for g in GOALS],
        })
        _save(d)
        print("homeostasis: ОПЕРАЦИЯ ПЕРЕЗАПУЩЕНА · старт %s · срок %s"
              % (d["started_msk"], d["deadline_msk"]))
        return 0
    if not d or d.get("cleared"):
        sys.stderr.write("homeostasis: операция не запущена (нет состояния или "
                         "cleared) — сначала --relaunch\n")
        return 0 if d.get("cleared") else 2

    waits = _waits_facts()
    unread = _unread_facts()
    guard = _guard_facts()
    started = d.get("started_msk") or "?"
    deadline = d.get("deadline_msk") or "?"
    overdue_op = _now() > dt.datetime.strptime(deadline, "%Y-%m-%d %H:%M МСК") \
        .replace(tzinfo=MSK) if deadline != "?" else False

    facts = [
        "СТАРТ: %s · СРОК: %s%s" % (started, deadline,
                                    " — СРОК ПРОШЁЛ" if overdue_op else ""),
        "Ожидания (реестр): открыто %d · просрочено %d · должны мне %d"
        % (waits["open"], waits["overdue"], waits["owed_by_me"]),
        "Непрочитанные письма: %d · самое старое %d мин%s"
        % (unread["count"], unread["oldest_min"],
           " — ДЕФЕКТ (порог %d)" % UNREAD_LIMIT_MIN
           if unread["oldest_min"] > UNREAD_LIMIT_MIN else ""),
        "Сторож портала: %s · ошибок разбора за час: %d"
        % (guard["active"], guard["tl_errors_1h"]),
        "",
        "Просрочено сейчас:",
    ]
    facts += ["  " + l for l in waits["lines"][:10]] or ["  нет"]
    goals = [
        "",
        "ЦЕЛИ (канон ЦУ, cu-goals-canon-20261107):",
    ]
    for name, check in GOALS:
        goals.append("  %s — проверка: %s" % (name, check))
    goals += [
        "",
        "Вычислимо сейчас: G2 учёт — просрочено %d; G8 ночь — ошибок разбора %d;"
        % (waits["overdue"], guard["tl_errors_1h"]),
        "остальные цели требуют линий — прошу статус по каждой.",
    ]
    body = "\n".join(facts + goals)
    ping_no = int(d.get("pings", 0)) + 1
    head = ("---\ntype: Letter\ntitle: \"Пинг операции гомеостаз #%d: "
            "факты и цели\"\nref: %s\n---\n\n" % (ping_no, _ref(ping_no)))
    letter = head + (
        "## СДЕЛАНО\n1. Пингер v2: факты из реестра ожиданий, возраст "
        "непрочитанного, наблюдатель операции, восемь целей канона.\n\n"
        "## ЗАБЛОКИРОВАНО\n2. Цели, требующие линий — статус от линий.\n\n"
        "## ЖДЁТ-ЗАБОТЫ\n3. Статус по каждой из восьми целей и первая строка "
        "«закрыто».\n\n" + body + "\n\n"
        "После выполнения — продолжай свою работу.\n")

    if dry:
        print(letter)
        return 0

    import tempfile
    fd, path = tempfile.mkstemp(suffix=".md", prefix="homeostasis-ping-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(letter)
    try:
        proc = subprocess.run(
            [SHIP_MAIL, "send", "--to", CU_SID, "--from", MY_SID,
             "--title", "Пинг гомеостаза #%d: факты и цели" % ping_no,
             "--ref", _ref(ping_no), "--file", path],
            capture_output=True, text=True, timeout=180)
        ok = proc.returncode == 0
        if not ok:
            sys.stderr.write("homeostasis: отправка не удалась: %s\n"
                             % ((proc.stdout or "") + (proc.stderr or ""))[-300:])
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if not ok:
        d["last_send_error"] = _fmt(_now())
        _save(d)
        return 1
    d["pings"] = ping_no
    d["last_ping_msk"] = _fmt(_now())
    d.pop("last_send_error", None)
    _save(d)
    print("homeostasis: пинг #%d отправлен (%s)" % (ping_no, d["last_ping_msk"]))
    return 0


def _ref(n: int) -> str:
    return "homeostasis-ping-20261108-%03d" % n


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
