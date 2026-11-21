#!/usr/bin/env python3
"""Compact one-line summary of a key-rotator watch.py result for the dunst alert.

Reads the JSON the watcher prints on stdout (or nothing) and prints one line:
    статус: <status> | упавшие: <aliases> | классы: <log_errors>
Never fails: unreadable input becomes "нет данных".
"""
import json
import sys


def summarize(raw: str) -> str:
    try:
        d = json.loads(raw or "{}")
    except Exception:
        return "нет данных"
    # Две разные причины деградации, разными строками (по договорённости с
    # Ротатором 20.11): УПАВШИЕ — smoke не ответил 200 (красный); МЕДЛЕННЫЕ —
    # ответил 200, но медленнее порога `slow_alias:<alias>:<ms>` (жёлтый).
    bad = [a.get("alias") for a in d.get("aliases", []) if not a.get("ok")]
    slow = [
        # Единицу несёт само предупреждение (`slow_alias:<alias>:<N>ms`) —
        # добавлять свою значило бы удвоение единиц в одном токене.
        f"{part[1]}={part[2]}"
        for w in d.get("warnings", [])
        for part in [str(w).split(":")]
        if part[0] == "slow_alias" and len(part) >= 3
    ]
    return (
        f"статус: {d.get('status')} | "
        f"упавшие: {(', '.join(str(a) for a in bad)) or 'нет'} | "
        f"медленные: {(', '.join(slow)) or 'нет'} | "
        f"классы: {d.get('log_errors', {})}"
    )


if __name__ == "__main__":
    print(summarize(sys.stdin.read()))