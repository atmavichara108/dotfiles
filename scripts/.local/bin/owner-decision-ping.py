#!/usr/bin/env python3
"""owner-decision-ping — таймер пинга владельцу по висящему слову.

Канон (слово владельца 2026-11-05): пока его слово по пункту висит — пинг в
портал (топик «Статусы») раз в 5 часов. Пинг ставит машина, не память агента:
именно поэтому он и не выполнялся, пока сторож был мёртв.

Состояние — один файл ~/.local/state/portal-tg/owner-decisions.json:
  {"cleared": false, "last_ping_msk": "...", "items": ["..."]}
Владелец ответил (или пункты сняты) — cleared=true, пинги прекращаются.
Отправка идёт через portal-tg-send.py (профиль portal), без секретов в логе.
"""
from __future__ import annotations

import json
import os
import sys
import time

STATE = os.path.expanduser("~/.local/state/portal-tg/owner-decisions.json")
SEND = os.path.expanduser("~/dotfiles/scripts/.local/bin/portal-tg-send.py")
TOPIC = 9          # «Статусы»
INTERVAL_H = 5
MARK = "last_ping_msk"

USAGE = ("owner-decision-ping --check | --init <json-file> | --clear | "
         "--dry-run\n"
         "  --check   при необходимости отправить пинг и обновить отметку\n"
         "  --init    заполнить список из файла-json (или заменить)\n"
         "  --clear   пометить, что слово владельца получено: пинги стоп\n"
         "  --dry-run показать, что было бы отправлено\n")


def _load() -> dict:
    try:
        with open(STATE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:  # noqa: BLE001 — нет файла = нечего пинговать
        pass
    return {"cleared": True, "items": [], MARK: None}


def _save(data: dict) -> None:
    tmp = STATE + ".tmp"
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


def _parse_msk(value: str | None) -> float:
    """«2026-11-05 17:25 МСК» -> epoch (UTC+3), мусор/нет -> 0."""
    if not value:
        return 0.0
    try:
        date_part, _, time_part = value.partition(" ")
        y, mo, d = (int(x) for x in date_part.split("-"))
        hh, mm = (int(x) for x in time_part.split(":"))
        return time.mktime((y, mo, d, hh, mm, 0, 0, 0, -1)) - 3 * 3600
    except Exception:  # noqa: BLE001
        return 0.0


def _now_msk() -> str:
    return time.strftime("%Y-%m-%d %H:%M МСК",
                         time.gmtime(time.time() + 3 * 3600))


def _ping_text(data: dict) -> str:
    items = data.get("items") or []
    lines = [
        "Кэп, пинг по таймеру: твоё слово всё ещё висит (раз в 5 часов).",
        "",
    ]
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item}")
    lines += [
        "",
        "Ответь номерами, и я снимаю пункты со таймера.",
        "Если пункт больше не актуален — скажи «снять», перестану пинговать.",
        "",
        "— AllIs Maya · ref: owner-decision-ping",
    ]
    return "\n".join(lines)


def _send(text: str) -> int:
    import subprocess
    env = dict(os.environ, TG_PROFILE="portal")
    proc = subprocess.run(["python3", SEND, "--topic", str(TOPIC),
                           "--reply-to", "0", "--format", "md",
                           "--text", text],
                          capture_output=True, text=True, env=env, timeout=120)
    tail = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        sys.stderr.write("owner-decision-ping: отправка не удалась: %s\n"
                         % tail[-300:])
        return 1
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("--check", "--init", "--clear", "--dry-run",
                                    "-h", "--help"):
        print(USAGE)
        return 0
    flag = argv[0]
    if flag in ("-h", "--help"):
        print(USAGE)
        return 0
    if flag == "--init":
        if len(argv) < 2:
            sys.exit("--init требует путь к json-файлу")
        with open(argv[1], encoding="utf-8") as f:
            fresh = json.load(f)
        data = _load()
        data["items"] = [str(x) for x in fresh.get("items", [])]
        data["cleared"] = bool(fresh.get("cleared", False))
        data[MARK] = fresh.get(MARK) or data.get(MARK)
        _save(data)
        print("owner-decision-ping: список обновлён (%d пунктов), cleared=%s"
              % (len(data["items"]), data["cleared"]))
        return 0
    data = _load()
    if flag == "--clear":
        data["cleared"] = True
        data[MARK] = _now_msk()
        _save(data)
        print("owner-decision-ping: пинги остановлены (cleared)")
        return 0
    if data.get("cleared") or not data.get("items"):
        return 0
    last = _parse_msk(data.get(MARK))
    now = time.time()
    if now - last < INTERVAL_H * 3600:
        return 0
    text = _ping_text(data)
    if flag == "--dry-run":
        print(text)
        return 0
    if _send(text) != 0:
        return 1
    data[MARK] = _now_msk()
    _save(data)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
