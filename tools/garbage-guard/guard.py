#!/usr/bin/env python3
"""Garbage-guard — детектор decode-мусора в контенте (инцидент 2026-10-07).

Root cause факта: LLM-провайдеры иногда выдают mojibake-всплески (Han/kana/
Hangul/Thai/FFFD внутри русско-английского контента). Детерминированный
zero-LLM гейт на трёх точках: staged-коммиты (pre-commit гейт 6), текст
письма (letter.sh REFUSE), ad-hoc проверка.

Правило: любой символ запрещённого класса вне whitelist-фрагментов — FAIL.
Whitelist fragment-level (по образцу maya-lint): точное вхождение фразы в
файл разрешает её целиком. Легитимного CJK-контента в dotfiles нет — ложных
срабатываний не ожидается; исторические артефакты (битые вставки) перечислены
в config.json.

Команды:
    guard.py scan --staged           # все staged-файлы (pre-commit)
    guard.py scan --path <p>...      # явные файлы/директории
    guard.py check-text              # текст из stdin (letter.sh)
    guard.py allowlist               # показать whitelist (debug)
Exit: 0 чисто | 1 мусор | 2 ошибка ввода.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).resolve().parent / "config.json"

# Классы decode-мусора: CJK-идеограммы, кана, хангыль, тай + replacement.
import re

BANNED = re.compile(
    "[\u4e00-\u9fff\u3040-\u30ff\u31f0-\u31ff"  # Han, hiragana, katakana
    "\uac00-\ud7af\u1100-\u11ff"                  # Hangul
    "\u0e00-\u0e7f"                               # Thai
    "\ufffd]"                                     # replacement char
)

# Латинический класс (мандат Дирижёра 2026-10-07): кириллическое слово с
# вклинившейся латиницей (гомоглифы/decode-вставки: agеnt, хello, дублиca).
# Токен = максимальная буквенная цепочка; flagged, если содержит ОБА скрипта
# без разделителя. Естественный code-switching (letter.sh, task/*, пробел,
# дефис) токеном не является — ноль ложных на прозе (проверено: 0/6 писем).
WORD = re.compile(r"[A-Za-z\u0400-\u04ff]+")
CYRILLIC = re.compile(r"[\u0400-\u04ff]")
LATIN = re.compile(r"[A-Za-z]")


def find_latin_mix(text: str) -> list[tuple[int, str]]:
    hits = []
    for m in WORD.finditer(text):
        w = m.group(0)
        if not (CYRILLIC.search(w) and LATIN.search(w)):
            continue
        # escape-последовательности (\nЗ, \tр): одиночная латиница за бэкслешем
        if m.start() > 0 and text[m.start() - 1] == "\\":
            continue
        hits.append((m.start(), w))
    return hits


def load_config() -> dict:
    if not CONFIG.exists():
        return {}
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def excluded(label: str, prefixes: list[str]) -> bool:
    return any(label == p or label.startswith(p) for p in prefixes)


def load_allowlist() -> list[dict]:
    return load_config().get("fragments", [])


def self_exempt(label: str) -> bool:
    """Эталон не проверяется самим собой: whitelist-конфиг и детектор
    легально содержат CJK-образцы (иначе guard ловит сам себя)."""
    return label in {"tools/garbage-guard/config.json", "tools/garbage-guard/guard.py"}


def get_excludes() -> list[str]:
    return load_config().get("exclude_prefixes", [])


def allow_spans(text: str, file_label: str, allowlist: list[dict]) -> list[tuple[int, int]]:
    """Диапазоны разрешённых вхождений для файла."""
    spans: list[tuple[int, int]] = []
    for entry in allowlist:
        if entry.get("path") and entry["path"] != file_label:
            continue
        frag = entry.get("fragment") or ""
        if not frag:
            continue
        start = text.find(frag)
        while start != -1:
            spans.append((start, start + len(frag)))
            start = text.find(frag, start + 1)
    return spans


def in_spans(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in spans)


def find_banned(text: str, file_label: str, allowlist: list[dict]) -> list[dict]:
    spans = allow_spans(text, file_label, allowlist)
    hits = []
    for m in BANNED.finditer(text):
        if in_spans(m.start(), spans):
            continue
        line_no = text.count("\n", 0, m.start()) + 1
        ch = m.group(0)
        hits.append({
            "path": file_label,
            "line": line_no,
            "char": ch,
            "name": unicodedata.name(ch, "?"),
            "context": text[max(0, m.start() - 30):m.start() + 30].replace("\n", "|"),
        })
    # латинический класс: смешанные токены (whitelist-спан тоже применяется)
    for pos, word in find_latin_mix(text):
        if in_spans(pos, spans):
            continue
        line_no = text.count("\n", 0, pos) + 1
        hits.append({
            "path": file_label,
            "line": line_no,
            "char": word,
            "name": "latin-cyrillic-mix",
            "context": text[max(0, pos - 30):pos + 30].replace("\n", "|"),
        })
    # группируем соседние символы одного всплеска (Han в слове = один hit на строку)
    merged: dict[tuple[str, int], dict] = {}
    for h in hits:
        key = (h["path"], h["line"])
        if key in merged:
            merged[key]["char"] += h["char"]
            merged[key]["name"] = "mixed"
        else:
            merged[key] = dict(h)
    return list(merged.values())


def read_staged() -> list[tuple[str, str]]:
    names = subprocess.run(
        ["git", "-C", str(REPO), "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True, check=False,
    ).stdout.splitlines()
    excludes = get_excludes()
    out = []
    for n in names:
        if self_exempt(n) or excluded(n, excludes):
            continue
        data = subprocess.run(
            ["git", "-C", str(REPO), "show", f":{n}"],
            capture_output=True, check=False,
        )
        if data.returncode == 0:
            try:
                out.append((n, data.stdout.decode("utf-8")))
            except UnicodeDecodeError:
                pass  # бинарник
    return out


def read_paths(paths: list[str]) -> list[tuple[str, str]]:
    excludes = get_excludes()
    out = []
    for p in paths:
        path = Path(p)
        if not path.is_absolute():
            path = REPO / path
        files = [path] if path.is_file() else sorted(path.rglob("*"))
        for f in files:
            if not f.is_file():
                continue
            if "node_modules" in f.parts or ".git" in f.parts:
                continue  # вендорные библиотеки легально содержат CJK-локали
            try:
                label = str(f.relative_to(REPO))
                if self_exempt(label) or excluded(label, excludes):
                    continue
                out.append((label, f.read_text(encoding="utf-8")))
            except (UnicodeDecodeError, ValueError, OSError):
                continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser(prog="guard.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("scan")
    g = s1.add_mutually_exclusive_group(required=True)
    g.add_argument("--staged", action="store_true")
    g.add_argument("--path", nargs="+")
    sub.add_parser("check-text")
    sub.add_parser("allowlist")
    args = ap.parse_args()

    allow = load_allowlist()

    if args.cmd == "allowlist":
        print(json.dumps(allow, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "check-text":
        text = sys.stdin.read()
        hits = find_banned(text, "<letter>", allow)
    else:
        sources = read_staged() if args.staged else read_paths(args.path)
        hits = []
        for label, text in sources:
            hits.extend(find_banned(text, label, allow))

    if hits:
        for h in hits[:20]:
            print(f"MOJIBAKE: {h['path']}:{h['line']} [{h['char']}] {h['name']} …{h['context']}…",
                  file=sys.stderr)
        if len(hits) > 20:
            print(f"MOJIBAKE: …и ещё {len(hits) - 20}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
