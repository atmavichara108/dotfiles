#!/usr/bin/env python3
"""lint_letter — линт письма Корабля перед отправкой (Р-090).

Проверяет (часть FAIL, часть WARN):
  FAIL:
    - type/from/to/ref/title присутствуют;
    - from/to — полные sessionID;
    - ref не пустой и уникален в журнале отправок (sent.jsonl);
    - номер мандата не занят и монотонен (если письмо несёт Р-N);
    - заголовки СДЕЛАНО / ЗАБЛОКИРОВАНО / ЖДЁТ-ЗАБОТЫ присутствуют;
    - письмо с действием оканчивается продолжением работы.
  WARN:
    - sha256 в тексте без пути к файлу;
    - ссылки на локальные пути, которых нет на диске.

Выход: 0 — WARN допустимы; 2 — FAIL; 1 — ошибка использования.
Формат вывода — строки LINT PASS/WARN/FAIL.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HOME = os.path.expanduser("~/.local/share/ship-mail")
SENT_LOG = os.path.join(HOME, "sent.jsonl")
MANDATE_JOURNAL = os.path.join(HOME, "mandate-numbers.jsonl")
SID_RE = re.compile(r"^ses_[A-Za-z0-9]{12,}$")
SHA_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
PATH_RE = re.compile(r"(?P<path>(?:/~|/)(?:[\w.-]+/)+[\w.-]*)")
CONTINUE_RE = re.compile(r"после выполнения[^\n]{0,80}продолж", re.IGNORECASE)
ACTION_RE = re.compile(r"(мандат|прошу|реализуй|исправь|нужно сделать|задача|диагности|докладывай|проверь|сделай)", re.IGNORECASE)
SECTION_PARTS = ("СДЕЛАНО", "ЗАБЛОКИРОВАНО", "ЖДЁТ")
MANDATE_RE = re.compile(r"\bР-(\d+)\b")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _sent_rows(path):
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def _mandate_rows():
    if not os.path.exists(MANDATE_JOURNAL):
        return []
    out = []
    for line in open(MANDATE_JOURNAL, encoding="utf-8"):
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def lint(args) -> int:
    warns: list[str] = []
    fails: list[str] = []

    if not args.type:
        fails.append("type пустой")
    if not args.title:
        fails.append("title пустой")
    if not args.ref:
        fails.append("ref пустой")
    if not args.from_:
        fails.append("from пустой")
    if not args.to:
        fails.append("to пустой")
    if args.from_ and not SID_RE.fullmatch(args.from_):
        fails.append("from не полный sessionID: %s" % args.from_)
    if args.to and not SID_RE.fullmatch(args.to):
        fails.append("to не полный sessionID: %s" % args.to)

    for row in _sent_rows(SENT_LOG):
        if row.get("ref") == args.ref:
            fails.append("ref %s уже отправлен письмом %s" % (args.ref, row.get("id")))

    body = _read(args.file) if args.file else sys.stdin.read()
    text = " ".join(body.split())

    for part in SECTION_PARTS:
        if part not in body:
            fails.append("нет раздела %s" % part)

    has_action = bool(ACTION_RE.search(text))
    if has_action or args.require_continue:
        if not CONTINUE_RE.search(text):
            fails.append("письмо с действием не оканчивается продолжением работы")
    # Р-Н: номер мандата должен быть свободен и монотонен
    m = MANDATE_RE.search(text)
    if m:
        num = m.group(1)
        rows = _mandate_rows()
        same = [r for r in rows if str(r.get("number")) == num]
        if same:
            fails.append("номер мандата Р-%s уже занят письмом %s" % (num, same[0].get("id")))
        nums = [int(r["number"]) for r in rows if str(r.get("number", "")).isdigit()]
        if nums and int(num) <= max(nums):
            fails.append("номер мандата Р-%s не монотонен (максимум %d)" % (num, max(nums)))

    if SHA_RE.search(text):
        # sha256 без локального пути — только предупреждение, не блок
        if not re.search(r"(путь|file|файл)[^\n]{0,80}(/|~)", text):
            warns.append("sha256 без пути к существующему файлу — проверь evidence")

    for pm in PATH_RE.finditer(body):
        p = pm.group("path").rstrip(").,«»\"'")
        if p.startswith("~/"):
            p = os.path.expanduser(p)
        if pm.group("path").startswith("/home/rudra/Projects"):
            # ссылки в чужие проекты могут не существовать локально — предупреждение
            if not os.path.exists(p):
                warns.append("ссылка не найдена на диске: %s" % p)
        elif not os.path.exists(p):
            warns.append("ссылка не найдена на диске: %s" % p)

    for w in warns:
        print("WARN lint-letter: %s" % w)
    for f in fails:
        print("FAIL lint-letter: %s" % f)

    if fails:
        print("LINT FAIL (%d fails, %d warns)" % (len(fails), len(warns)))
        return 2
    if warns:
        print("LINT WARN (%d warns)" % len(warns))
        return 0
    print("LINT PASS")
    return 0


def main():
    ap = argparse.ArgumentParser(prog="lint_letter")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file")
    src.add_argument("--stdin", action="store_true")
    ap.add_argument("--type", default="Letter")
    ap.add_argument("--title", default="letter")
    ap.add_argument("--ref", default="")
    ap.add_argument("--from", dest="from_", default="")
    ap.add_argument("--to", default="")
    ap.add_argument("--require-continue", action="store_true")
    a = ap.parse_args()
    return lint(a)


if __name__ == "__main__":
    raise SystemExit(main())
