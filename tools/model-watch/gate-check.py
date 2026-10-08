#!/usr/bin/env python3
"""Гейт свежести каталога моделей: exit 1 если снапшот отсутствует или старше N дней.

Обход: MODEL_OK=1 python3 gate-check.py
Хук в волт подключается ОТДЕЛЬНЫМ шагом (этот скрипт — только проверка).
"""
import json
import os
import sys
import time
from pathlib import Path

SNAP = Path(os.environ.get(
    "MODEL_WATCH_SNAPSHOT",
    Path.home() / "Projects/OpenCode-Vault/control-plane/model-catalog.json",
))
MAX_AGE_DAYS = int(os.environ.get("MODEL_WATCH_MAX_AGE_DAYS", "7"))


def main() -> int:
    if os.environ.get("MODEL_OK") == "1":
        print("gate: PASS (MODEL_OK=1 bypass)")
        return 0
    if not SNAP.exists():
        print(f"gate: FAIL — снапшот отсутствует: {SNAP}")
        return 1
    try:
        gen = json.loads(SNAP.read_text()).get("generated_at", "")
        ts = time.mktime(time.strptime(gen[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, KeyError, json.JSONDecodeError):
        print(f"gate: FAIL — не читается generated_at в {SNAP}")
        return 1
    age_days = (time.time() - ts) / 86400
    if age_days > MAX_AGE_DAYS:
        print(f"gate: FAIL — снапшот устарел: {age_days:.1f} дн > {MAX_AGE_DAYS} дн")
        return 1
    print(f"gate: PASS — снапшот свежий ({age_days:.1f} дн)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
