#!/usr/bin/env python3
"""package-guard — блок установок пакетов вне allowlist (мандат СБ C3).

Безопасная поставка: агент не должен ставить пакеты «свежего» возраста или
неизвестные. allowlist держит владелец/инженерный контур. Свежесть по умолчанию
7 дней, но основное правило СБ: нет в allowlist — нет установки без явного
слова владельца; осознанный обход — `PACKAGE_OK=1`.

Использование:
  package-guard.py check --cmd "<полная команда>"
Коды:
  0 — разрешено; 2 — заблокировано; 1 — ошибка разбора команды.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

DEFAULT_CONFIG = os.path.expanduser("~/.config/opencode/agent-package-allowlist.json")
DEFAULT_ALLOW = []
DEFAULT_FRESH_DAYS = 7
NPM = "https://registry.npmjs.org/"
PYPI = "https://pypi.org/pypi/"


def _load_config():
    if os.path.exists(DEFAULT_CONFIG):
        try:
            d = json.load(open(DEFAULT_CONFIG, encoding="utf-8"))
            return set(d.get("allow", [])), int(d.get("fresh_days", DEFAULT_FRESH_DAYS))
        except Exception as err:  # noqa: BLE001
            print(f"PACKAGE-GUARD FAIL: allowlist битый: {err}", file=sys.stderr)
            sys.exit(2)
    return set(DEFAULT_ALLOW), DEFAULT_FRESH_DAYS


def _packages_from_cmd(cmd: str):
    c = cmd.strip()
    low = c.lower()
    # pip install [options] pkg==1 ...
    m = re.search(r"(?:^|[\s;&|])(?:sudo\s+)?(?:-m\s+)?(?:python[0-9.]*\s+-m\s+)?pip[0-9.]*\s+install\s+(.*)$", low)
    if m:
        rest = m.group(1)
        toks = rest.split()
        out = []
        skip_next = False
        for i, t in enumerate(toks):
            if skip_next:
                skip_next = False
                continue
            if t in ("-r", "--requirement", "-c", "--constraint", "-t", "--target"):
                skip_next = True
                continue
            if t.startswith("-"):
                continue
            if t in ("install", "python", "-m"):
                continue
            if t.startswith("http://") or t.startswith("https://") or t.startswith("git+"):
                out.append({"name": t, "version": "", "registry": "url"})
                continue
            name = re.split(r"[=<>!~ ]", t, maxsplit=1)[0]
            version = t[len(name):].lstrip("=<>~! ")
            if name:
                out.append({"name": name, "version": version, "registry": "pypi"})
        return out
    # npm install / pnpm install/add / yarn add
    m = re.search(r"(?:^|[\s;&|])(?:npm|pnpm|yarn)\s+(?:install|i|add|dlx)\s+(.*)$", low)
    if m:
        rest = m.group(1)
        # сохранить исходные токены командной строки (без shell-переносов)
        toks = rest.split()
        out = []
        skip_next = False
        for t in toks:
            if skip_next:
                skip_next = False
                continue
            if t.startswith("-"):
                continue
            if t.startswith("http://") or t.startswith("https://") or t.startswith("git+") or t.startswith("file:"):
                out.append({"name": t, "version": "", "registry": "url"})
                continue
            if "@" in t and not t.startswith("@"):
                name, version = t.split("@", 1)
                out.append({"name": name, "version": version, "registry": "npm"})
            elif t.startswith("@"):
                out.append({"name": t, "version": "", "registry": "npm"})
            else:
                out.append({"name": t, "version": "", "registry": "npm"})
        return out
    return []


def _http_json(url: str):
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode())
    except Exception as err:  # noqa: BLE001
        return {"__error__": f"{type(err).__name__}: {err}"}


def _iso_to_ts(s: str):
    try:
        return time.mktime(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:  # noqa: BLE001
        return None


def _freshness(pkg):
    name = pkg["name"]
    reg = pkg.get("registry", "")
    if reg == "url":
        return None, "url/path not checked"
    if reg == "pypi":
        d = _http_json(PYPI + name + "/json")
        if "__error__" in d:
            return None, f"pypi unreachable: {d['__error__']}"
        times = []
        for files in (d.get("releases") or {}).values():
            for f in files or []:
                t = f.get("upload_time")
                if t:
                    ts = _iso_to_ts(t)
                    if ts:
                        times.append(ts)
        if not times:
            return None, "no published release date"
        return round((time.time() - min(times)) / 86400, 1), "pypi first upload"
    d = _http_json(NPM + name)
    if "__error__" in d:
        return None, f"npm unreachable: {d['__error__']}"
    created = d.get("time", {}).get("created")
    if created:
        ts = _iso_to_ts(created)
        if ts:
            return round((time.time() - ts) / 86400, 1), "npm created"
    return None, "no npm created date"


def cmd_check(a):
    allow, fresh_days = _load_config()
    pkgs = _packages_from_cmd(a.cmd)
    if not pkgs:
        print("PACKAGE-GUARD ALLOW: команда не распознана как установка пакета")
        return 0
    blocked = []
    for p in pkgs:
        if p["name"] in allow:
            continue
        age, basis = _freshness(p)
        fresh = age is not None and age < fresh_days
        if fresh:
            blocked.append(f"{p['name']} — «свежий» пакет {age}д (<{fresh_days}д)")
        else:
            detail = f"{basis}: {age}д" if age is not None else basis
            blocked.append(f"{p['name']} — нет в allowlist ({detail})")
    if blocked:
        print("PACKAGE-GUARD BLOCK: агентская установка запрещена без allowlist/слова владельца:", file=sys.stderr)
        for b in blocked:
            print(f"  - {b}", file=sys.stderr)
        print("Легит: добавь пакет в allowlist или явное PACKAGE_OK=1 с причиной.", file=sys.stderr)
        return 2
    print("PACKAGE-GUARD ALLOW: пакеты в allowlist")
    return 0


def main():
    ap = argparse.ArgumentParser(prog="package-guard")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--cmd", required=True)
    a = ap.parse_args()
    return cmd_check(a)


if __name__ == "__main__":
    raise SystemExit(main())
