#!/usr/bin/env python3
"""ship-order — мини-диалог «точка карты → команда линии» (канон Р-117, мой кусок).

Зачем: приказ владельца должен уходить линию одной строкой, а не собираться
руками. Команда делает четыре шаги без участия памяти агента:

  1. найти линию по имени (или sid) в реестре пиров волта;
  2. составить письмо по канону (слово владельца дословно + разделы
     СДЕЛАНО / ЗАБЛОКИРОВАНО / ЖДЁТ-ЗАБОТЫ + строка «продолжай работу»);
  3. отправить через ship-mail (линт проверяется там же);
  4. записать факт в persist своей сессии (чтобы порядок хода это видел).

Использование:
  ship-order.py --to <линия|sid> --text "<задача>" [--ref REF]
                [--basis quoted] [--dry-run] [--pretty]

Пример:
  ship-order.py --to "Бизнес-школа" --text "свести чеки бирж по разделам" \\
      --ref market-checks-20261107

Секретов не принимает и не печатает. Тело письма — только то, что сказал
человек, плюс обвязка канона.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

VAULT = os.environ.get("OPENCODE_VAULT",
                       os.path.expanduser("~/Projects/OpenCode-Vault"))
PEER_REGISTRY = os.path.join(VAULT, "04-Memory", "peer-registry.md")
SHIP_MAIL = os.path.expanduser("~/.local/bin/ship-mail.sh")
PERSIST = os.path.expanduser("~/dotfiles/tools/ship-mail/persist.py")
MY_SID = os.environ.get("OPENCODE_SESSION_ID",
                        "ses_e714b5c4bffeh1ri37WHF8Q7Bx")
FROM_SID = os.environ.get("SHIP_MAIL_FROM", MY_SID)

USAGE = __doc__


def _peers() -> dict[str, dict]:
    """Имя линии -> {sid, agent, dir, role}. Реестр — источник правды."""
    out: dict[str, dict] = {}
    try:
        text = open(PEER_REGISTRY, encoding="utf-8").read()
    except OSError:
        return out
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0].lower() in ("ведомство", ""):
            continue
        if not re.match(r"^ses_", cells[1] or ""):
            continue
        out[cells[0]] = {"sid": cells[1], "agent": cells[2] if len(cells) > 2 else "",
                         "dir": cells[3] if len(cells) > 3 else "",
                         "role": cells[4] if len(cells) > 4 else ""}
    return out


def resolve(target: str) -> dict:
    peers = _peers()
    if target.startswith("ses_"):
        for name, p in peers.items():
            if p["sid"] == target:
                return {"name": name, **p}
        return {"name": target, "sid": target, "agent": "", "dir": "",
                "role": ""}
    low = target.lower()
    for name, p in peers.items():
        if low in name.lower():
            return {"name": name, **p}
    for name, p in peers.items():           # короткие формы: цу, ипт, ис
        short = re.sub(r"[^\u0430-\u044f\u0451\u0401a-z]", "", name.lower())
        if low and low in short:
            return {"name": name, **p}
    return {}


def letter_text(line: dict, task: str, ref: str, basis: str) -> str:
    who = line["name"]
    agent = line.get("agent") or "линия"
    return f"""---
type: Letter
title: "Поручение из мини-диалога: {who}"
ref: {ref}
---

AllIs Maya → {who} ({line['sid']}).

СЛОВО ВЛАДЕЛЬЦА (basis: {basis}): «{task}»

ПОРУЧЕНИЕ (одно действие): {task}.

СДЕЛАНО:
1. Поручение принято строкой из мини-диалога карты и отправлено адресно этой
   линией; факт записан на диск сразу.

ЗАБЛОКИРОВАНО:
2. Обязательства, деньги, внешние аккаунты и всё необратимое — только слово
   владельца. Если поручение в этой зоне — скажите, я верну его людому.

ЖДЁТ-ЗАБОТЫ:
3. Ответ линии строкой: что взято, в каком сроке, что нужно от владельца.
   Молчание — дефект; если строка повиснет, верну её владельцу с таймером.

После выполнения — продолжай свою работу.

— AllIs Maya · мини-диалог (канон Р-117) · агент линии: {agent}
"""


def main(argv: list[str]) -> int:
    args: dict[str, str] = {}
    dry = "--dry-run" in argv
    key = None
    for a in argv:
        if a.startswith("--"):
            key = a[2:]
        elif key:
            args[key] = a
            key = None
    target = args.get("to", "")
    task = args.get("text", "")
    ref = args.get("ref") or "order-%s" % re.sub(r"\W", "", target)[:12] or "order"
    basis = args.get("basis", "quoted")

    if not target or not task or "-h" in argv or "--help" in argv:
        print(USAGE)
        return 0 if not (target and task) else 0

    line = resolve(target)
    if not line:
        sys.stderr.write("ship-order: линия не найдена в реестре пиров: %r\n"
                         "Список линий: %s\n"
                         % (target, ", ".join(sorted(_peers()))))
        return 2
    if line["sid"] == FROM_SID:
        sys.stderr.write("ship-order: это Моя линия — поручение себе не нужно\n")
        return 2

    body = letter_text(line, task, ref, basis)
    if dry:
        print("--- ПРОВЕРКА (не отправлено) ---")
        print(body)
        return 0

    fd, path = tempfile.mkstemp(suffix=".md", prefix="ship-order-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body)
    try:
        proc = subprocess.run(
            [SHIP_MAIL, "send", "--to", line["sid"], "--from", FROM_SID,
             "--title", "Поручение из мини-диалога: %s" % line["name"],
             "--ref", ref, "--file", path],
            capture_output=True, text=True, timeout=180)
        tail = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            sys.stderr.write("ship-order: отправка не прошла:\n%s\n" % tail[-400:])
            return 1
        print("ship-order: %s (%s) — поручение ушло · ref=%s"
              % (line["name"], line["sid"], ref))
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    try:
        subprocess.run(["python3", PERSIST, "write", "--sid", MY_SID,
                        "--kind", "note", "--ref", ref,
                        "--text", "Мини-диалог: поручение «%s» отправлено линии %s (%s)"
                        % (task[:160], line["name"], line["sid"])],
                       capture_output=True, timeout=60)
    except Exception:  # noqa: BLE001 — persist не блокирует отправку
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
