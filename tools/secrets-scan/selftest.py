#!/usr/bin/env python3
"""selftest secrets-scan — воспроизводимая проверка DoD мандата C3.

Три случая:
  1. тестовая «утечка» в файле ловится (rc=2);
  2. чистый файл проходит (rc=0);
  3. маркер `secrets-scan:allow` в строке снимает блок (rc=0).

Образцы секретов ниже — нерабочие строки-образцы, allowlist закрывает путь.
Запуск: python3 tools/secrets-scan/selftest.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

SCAN = Path(__file__).with_name("scan.py")

LEAK = "API_TOKEN=supersecretvalue123456\n"
CLEAN = "NOTHING=public\n"
ALLOWED = "API_TOKEN=supersecretvalue123456  # secrets-scan:allow (образец)\n"


def run(text: str) -> int:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        fh.write(text)
        name = fh.name
    try:
        return subprocess.run([sys.executable, str(SCAN), name]).returncode
    finally:
        Path(name).unlink(missing_ok=True)


def main() -> int:
    cases = [
        ("leak blocked", LEAK, 2),
        ("clean passes", CLEAN, 0),
        ("marker allows", ALLOWED, 0),
    ]
    bad = 0
    for name, text, want in cases:
        got = run(text)
        ok = got == want
        bad += 0 if ok else 1
        print(f"{'✅' if ok else '❌'} {name}: rc={got} (ожидали {want})")
    print("SELFTEST FAIL" if bad else "SELFTEST PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
