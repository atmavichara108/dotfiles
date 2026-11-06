#!/usr/bin/env python3
"""secrets-scan — блокирующий пре-коммит скан секретов (мандат СБ C3).

Замена внешним gitleaks/trufflehog до их внедрения: высокочастотные сигналы
секретов в staged-файлах. Не заменяет полноценный сканер, но закрывает класс
«токен в коммите».

Правила:
  - блокирующий режим;
  - исключения — строка-маркер `secrets-scan:allow` в файле или путь из allowlist;
  - осознанный обход: `SECRET_SCAN_OK=1` у хука (причина — в сообщении коммита).

Использование:
  scan.py --staged           # сканировать staged-файлы текущего репозитория
  scan.py <file> [<file>...] # явить выбранные файлы
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ALLOWLIST = Path(__file__).with_name("allowlist.json")

PATTERNS = [
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("telegram-bot-token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    ("resend-key", re.compile(r"\bre_[A-Za-z0-9]{20,}\b")),
    ("github-app-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("aws-secret", re.compile(r"\bAWS(?:SECRET|_SECRET)?[_-]?ACCESS[_-]?KEY[_-]?ID\b\s*[:=]\s*\S{12,}", re.IGNORECASE)),
    ("generic-secret", re.compile(
        r"(?i)\b(?:[A-Za-z0-9_]*(?:secret|token|password|passwd|passphrase|api[_-]?key|access[_-]?key|client[_-]?secret|auth[_-]?token)[A-Za-z0-9_]*)\s*[:=]\s*['\"]?[A-Za-z0-9._-]{12,}")),
    ("secret-assignment", re.compile(
        r"(?i)\b(?:[A-Za-z0-9_]*secret[A-Za-z0-9_]*|[A-Za-z0-9_]*token[A-Za-z0-9_]*)\b\s*[:=]\s*\S{12,}")),
    ("high-entropy-url-secret", re.compile(r"[?&](?:token|key|secret|password)=[A-Za-z0-9._-]{16,}")),
]
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".woff", ".woff2", ".ttf", ".zip", ".7z", ".pdf", ".ico", ".webp"}


def _allow_path(path: str) -> bool:
    try:
        if ALLOWLIST.exists():
            pats = json.load(open(ALLOWLIST, encoding="utf-8"))
            for p in pats.get("paths", []):
                if path == p or path.startswith(p if p.endswith("/") else p + "/"):
                    return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _staged_files():
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMRD"],
                         capture_output=True, text=True)
    return [f for f in out.stdout.splitlines() if f]


def _file_text(repo_file: str):
    if subprocess.run(["git", "cat-file", "-e", f":{repo_file}"], capture_output=True).returncode == 0:
        return subprocess.run(["git", "show", f":{repo_file}"], capture_output=True).stdout.decode("utf-8", "replace")
    try:
        return Path(repo_file).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _scan_text(text: str, path: str):
    findings = []
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        if "secrets-scan:allow" in line:
            continue
        for name, rx in PATTERNS:
            if rx.search(line):
                findings.append(f"{path}:{i} {name}")
    return findings


def main():
    args = sys.argv[1:]
    if not args:
        print("usage: scan.py --staged | <files>")
        return 1
    if args == ["--staged"]:
        files = _staged_files()
    else:
        files = args

    bad = []
    for f in files:
        if _allow_path(f):
            continue
        if Path(f).suffix.lower() in BINARY_EXT:
            continue
        text = _file_text(f)
        if not text:
            continue
        bad.extend(_scan_text(text, f))

    if bad:
        print("❌ secrets-scan: найдены признаки секретов:", file=sys.stderr)
        for b in bad[:50]:
            print("   " + b, file=sys.stderr)
        print("Исключение: маркер `secrets-scan:allow` в строке или allowlist.json.",
              file=sys.stderr)
        print("Осознанный обход: SECRET_SCAN_OK=1 с причиной в сообщении коммита.",
              file=sys.stderr)
        return 2
    print("✅ secrets-scan: staged чист")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
