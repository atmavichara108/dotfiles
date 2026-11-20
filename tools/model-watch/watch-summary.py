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
    bad = [a.get("alias") for a in d.get("aliases", []) if not a.get("ok")]
    return (
        f"статус: {d.get('status')} | "
        f"упавшие: {bad or 'нет'} | "
        f"классы: {d.get('log_errors', {})}"
    )


if __name__ == "__main__":
    print(summarize(sys.stdin.read()))