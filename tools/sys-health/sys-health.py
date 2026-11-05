#!/usr/bin/env python3
"""sys-health — тихий сторож служб и прокси (fail-open, без прав и секретов).

Инцидент 2026-11-05: TG-сторожа и proxy падали, но об этом узнавали постфактум.
Скрипт проверяет ключевые user-службы; если служба мертва — поднимает её и пишет
факт в журнал. Прокси правит отдельный proxy-healthcheck (mode auto); здесь только
сверка, не молчание.

Журнал: ~/dotfiles/logs/sys-health/sys-health.jsonl (меты-only).
Коды: 0 ок · 2 есть поднятые/неподнятые службы · 1 ошибка запуска.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
LOG_DIR = os.path.join(HOME, "dotfiles/logs/sys-health")
LOG = os.path.join(LOG_DIR, "sys-health.jsonl")
PROXY_MODE = os.path.join(HOME, ".config/proxyctl/mode")
PROXY_CONF = os.path.join(HOME, ".config/environment.d/proxy.conf")

SERVICES = [
    "portal-tg-guard.service",
    "serp-tg-guard.service",
    "dv-tg-guard.service",
    "tg-guard.service",
    "trademind-tg-guard.service",
    "captain-panel-bot.service",
]
PROXY_PORTS = [10808, 10809]  # HAPP только; Tor живёт отдельным chromium-tor


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _append(entry: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _is_active(unit: str) -> bool:
    r = subprocess.run(["systemctl", "--user", "is-active", unit],
                       capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "active"


def _port_open(port: int) -> bool:
    r = subprocess.run(["ss", "-ltn"], capture_output=True, text=True)
    return f":{port} " in r.stdout


def check_proxy() -> dict:
    mode = ""
    if os.path.exists(PROXY_MODE):
        mode = open(PROXY_MODE, encoding="utf-8").read().strip()
    conf = ""
    if os.path.exists(PROXY_CONF):
        conf = open(PROXY_CONF, encoding="utf-8").read()
    ports = {p: _port_open(p) for p in PROXY_PORTS}
    # HAPP — приоритет: оба порта обязательны, Tor не считается заменой.
    ok = ports.get(10808, False) and ports.get(10809, False) and mode in ("happ", "auto")
    return {"mode": mode or "unknown", "ports": ports, "ok": ok,
            "ALL_PROXY_in_conf": "ALL_PROXY" in conf}


def main() -> int:
    started, failed = [], []
    for unit in SERVICES:
        if _is_active(unit):
            continue
        subprocess.run(["systemctl", "--user", "start", unit],
                       capture_output=True, text=True)
        time.sleep(1)
        if _is_active(unit):
            started.append(unit)
        else:
            failed.append(unit)

    proxy = check_proxy()
    entry = {"ts": _now(), "class": "sys-health", "services": SERVICES,
             "started": started, "failed": failed, "proxy": proxy,
             "rc": 2 if (started or failed) else 0}
    if started or failed or not proxy["ok"]:
        _append(entry)

    if failed:
        print("SYS-HEALTH FAIL: не поднялись службы: " + ", ".join(failed))
        return 2
    if started:
        print("SYS-HEALTH STARTED: " + ", ".join(started))
        return 2
    print(f"SYS-HEALTH OK services={len(SERVICES)} proxy.mode={proxy['mode']} "
          f"ports={proxy['ports']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
