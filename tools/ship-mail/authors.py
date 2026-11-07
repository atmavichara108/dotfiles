#!/usr/bin/env python3
"""authors.py — карта почты: индекс авторов + срез «важное» (канон Р-117, мандат ЦУ).

Индекс: автор → вес (число писем), свежесть (первое/последнее), категории.
Категории — детерминированно по заголовку/ref: mandate / verdict / ping /
protocol / report / question / other.

Срез «важное»: письма Гитхаб-класса. Опознание — ТОЛЬКО по факту в письме:
  - фронтматтер `source: github` или `channel: github`, либо
  - в заголовке/теле упоминание github.com в контексте уведомления
    (issue/PR/actions/notifications).
Модель не участвует. Маршрут для Гитхаб-класса — ЦУ/ИС (прежнее слово
владельца): строка «ВАЖНОЕ → маршрут ЦУ/ИС».

Использование:
  authors.py                     # индекс авторов (короткий срез)
  authors.py --important         # срез «важное» + строки маршрута
  authors.py --measure           # замер: доля и число форм
  authors.py --sid <sid>         # только ящик одной сессии
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(os.environ.get(
    "SHIP_MAIL_ROOT",
    os.path.expanduser("~/.local/share/ship-mail/inbox")))

CAT_RULES = [
    ("mandate", re.compile(r"(?i)\bмандат\b|\bвердикт\b|\bприёмк")),
    ("ping", re.compile(r"(?i)\bпинг\b|просроч|overdue")),
    ("protocol", re.compile(r"(?i)\bпротокол\b|\bканон\b|Р-\d{2,3}")),
    ("report", re.compile(r"(?i)\bотчёт\b|сделано|рапорт|сверк")),
    ("question", re.compile(r"(?i)\bвопрос\b|уточн|нужно решени")),
]
GITHUB_FM = re.compile(r"(?im)^\s*(source|channel)\s*:\s*github\s*$")
GITHUB_TXT = re.compile(r"(?i)github\.com[^\s]*(?:issues|pull|actions|notifications)|\bgithub notification\b")


def _parse_fm(text: str):
    fm = {}
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return fm
    for line in m.group(1).splitlines():
        mm = re.match(r"^([A-Za-z_]+)\s*:\s*(.*)$", line)
        if mm:
            fm[mm.group(1)] = mm.group(2).strip().strip('"')
    return fm


def _category(title: str, ref: str, body: str):
    for name, rx in CAT_RULES:
        if rx.search(title) or (ref and rx.search(ref)):
            return name
    head = "\n".join(body.splitlines()[:25])
    for name, rx in CAT_RULES:
        if rx.search(head):
            return name
    return "other"


def _is_github(text: str, fm: dict):
    if GITHUB_FM.search(text):
        return True
    title = fm.get("title", "")
    if GITHUB_TXT.search(title):
        return True
    return bool(GITHUB_TXT.search("\n".join(text.splitlines()[:12])))


def letters(sid=None):
    dirs = [ROOT / sid] if sid else [p for p in ROOT.iterdir() if p.is_dir()] if ROOT.exists() else []
    out = []
    for d in dirs:
        if not d.is_dir():
            continue
        for sub in ("", "read"):
            base = d / sub if sub else d
            for f in sorted(base.glob("*.md")):
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                fm = _parse_fm(text)
                out.append({
                    "file": f, "fm": fm,
                    "from": fm.get("from", "?"),
                    "ts": fm.get("ts", ""),
                    "title": fm.get("title", ""),
                    "ref": fm.get("ref", ""),
                    "github": _is_github(text, fm),
                    "category": _category(fm.get("title", ""), fm.get("ref", ""), text),
                    "state": "read" if sub else "unread",
                })
    return out


def cmd_index(a):
    ls = letters(a.sid)
    by = defaultdict(lambda: {"n": 0, "first": None, "last": None, "cats": Counter()})
    for l in ls:
        d = by[l["from"]]
        d["n"] += 1
        d["cats"][l["category"]] += 1
        ts = l["ts"]
        if ts:
            d["first"] = min(d["first"] or ts, ts)
            d["last"] = max(d["last"] or ts, ts)
    print(f"АВТОРЫ: {len(by)} авторов, {len(ls)} писем")
    for who, d in sorted(by.items(), key=lambda kv: -kv[1]["n"])[:a.limit]:
        cats = ",".join(f"{k}:{v}" for k, v in d["cats"].most_common(3))
        print(f"  x{d['n']:<4} {who}  [{cats}]  свежесть: {d['first'][:10] if d['first'] else '?'} → {d['last'][:10] if d['last'] else '?'}")
    return 0


def cmd_important(a):
    ls = letters(a.sid)
    imp = [l for l in ls if l["github"]]
    print(f"ВАЖНОЕ (Гитхаб-класс): {len(imp)} из {len(ls)}")
    for l in imp:
        print(f"ВАЖНОЕ → маршрут ЦУ/ИС: {l['fm'].get('id', '?')} от {l['from']} "
              f"[{l['ts'][:16]}] {l['title'][:60]}")
    if not imp:
        print("Гитхаб-письем в хранилище нет — срез пуст (правило опознания заявлено "
              "в docstring: фронтматтер source/channel: github либо github.com в "
              "контексте уведомления). Модель не участвует, выдуманных писем нет.")
    return 0


def cmd_measure(a):
    ls = letters(a.sid)
    if not ls:
        print("ЗАМЕР: писем нет")
        return 0
    by = Counter(l["from"] for l in ls)
    top = by.most_common(3)
    share = sum(n for _, n in top) / len(ls) * 100
    cats = Counter(l["category"] for l in ls)
    imp = sum(1 for l in ls if l["github"])
    print(f"ЗАМЕР: писем {len(ls)}; авторов {len(by)}; категорий {len(cats)}; "
          f"доля топ-3 авторов {share:.1f}%; важное (Гитхаб) {imp}")
    print("  категории: " + ", ".join(f"{k}:{v}" for k, v in cats.most_common()))
    print("  топ-3: " + ", ".join(f"{who}({n})" for who, n in top))
    return 0


def main():
    ap = argparse.ArgumentParser(prog="authors")
    ap.add_argument("--important", action="store_true")
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--sid")
    ap.add_argument("--limit", type=int, default=12)
    a = ap.parse_args()
    if a.important:
        return cmd_important(a)
    if a.measure:
        return cmd_measure(a)
    return cmd_index(a)


if __name__ == "__main__":
    raise SystemExit(main())
