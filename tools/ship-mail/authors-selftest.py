#!/usr/bin/env python3
"""selftest authors — DoD карты почты (Р-117, мандат ЦУ ic-gate-and-galaxy).

Фикстуры во временном корне (SHIP_MAIL_ROOT): обычное письмо, письмо с
фронтматтером source: github, письмо с github.com в контексте уведомления.
Проверяет: индекс считает авторов и веса; категория детерминирована; срез
«важное» ловит оба Гитхаб-письма и даёт строку маршрута ЦУ/ИС.

Запуск: python3 tools/ship-mail/authors-selftest.py
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
_spec = importlib.util.spec_from_file_location("authors", HERE / "authors.py")
a = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(a)

NORMAL = """---
type: Letter
from: ses_A
to: ses_B
title: "вердикт по приёмке"
ts: 2026-11-07T10:00:00+03:00
id: n1
---
тело без гитхаба
"""

GITHUB_FM = """---
type: Letter
from: ses_GH
to: ses_B
source: github
title: "[repo] PR #12 opened"
ts: 2026-11-07T11:00:00+03:00
id: g1
---
notification body
"""

GITHUB_TXT = """---
type: Letter
from: ses_GH2
to: ses_B
title: "letter"
ts: 2026-11-07T12:00:00+03:00
id: g2
---
GitHub notification: https://github.com/org/repo/issues/42 комментарий
"""


def build(root: Path):
    for sid in ("ses_A",):
        d = root / sid
        (d / "read").mkdir(parents=True, exist_ok=True)
    (root / "ses_A" / "read" / "n1.md").write_text(NORMAL, encoding="utf-8")
    (root / "ses_A" / "g1.md").write_text(GITHUB_FM, encoding="utf-8")
    (root / "ses_A" / "g2.md").write_text(GITHUB_TXT, encoding="utf-8")


def main():
    bad = 0
    with tempfile.TemporaryDirectory(prefix="authorstest") as td:
        root = Path(td) / "inbox"
        root.mkdir(parents=True)
        build(root)
        env = dict(os.environ, SHIP_MAIL_ROOT=str(root))
        # индекс
        r = subprocess.run([sys.executable, str(HERE / "authors.py")],
                           capture_output=True, text=True, env=env)
        out = r.stdout
        for must in ("АВТОРЫ: 3 авторов, 3 писем", "x1", "ses_A"):
            if must not in out:
                print(f"❌ индекс: нет «{must}»:\n{out}")
                bad += 1
        # важное
        r = subprocess.run([sys.executable, str(HERE / "authors.py"), "--important"],
                           capture_output=True, text=True, env=env)
        out = r.stdout
        if "ВАЖНОЕ (Гитхаб-класс): 2 из 3" not in out:
            print(f"❌ важное: срез не дал 2 из 3:\n{out}")
            bad += 1
        if out.count("маршрут ЦУ/ИС") != 2:
            print(f"❌ важное: строк маршрута != 2:\n{out}")
            bad += 1
        # замер
        r = subprocess.run([sys.executable, str(HERE / "authors.py"), "--measure"],
                           capture_output=True, text=True, env=env)
        out = r.stdout
        for must in ("ЗАМЕР: писем 3", "важное (Гитхаб) 2"):
            if must not in out:
                print(f"❌ замер: нет «{must}»:\n{out}")
                bad += 1
    print("SELFTEST FAIL" if bad else "SELFTEST PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
