#!/usr/bin/env python3
"""release-watch — протокол «после каждого обновления OpenCode — фичи на апрув»
(слово владельца 2026-10-31).

Поток (три слоя, канон владельца):
  1. Как есть — сырые release notes апстрима.
  2. Предложения Мастерской — как это использовать в Корабле.
  3. Предложения владельца + проверка пригодности (Лаба) + внедрение (ИЦ/ЦУ).

Скрипт делает шаг 0 (детектор): раз в сутки сравнивает установленную версию
opencode с последним релизом апстрима (GitHub API). Новый релиз → письмо
в ящик Мастерской (ship-mail) с сырыми заметками релиза; разбор слоёв 2–3 —
работа агента при обработке письма, не скрипта.

Состояние: ~/.local/state/opencode/release-watch.json
Письмо: ship-mail send --to <Мастерская> (реестр peer-registry).
Сеть: GitHub API — напрямую, при неудаче через HTTP-прокси 10809
(канон скачиваний: socks/ALL_PROXY не использовать).

Коды выхода: 0 — нового нет/всё ок; 1 — новый релиз (письмо отправлено);
2 — ошибка сети/API (не фатально для таймера, видно в journal).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

STATE = os.path.expanduser("~/.local/state/opencode/release-watch.json")
REPO = os.environ.get("RELEASE_WATCH_REPO", "anomalyco/opencode")
HTTP_PROXY = os.environ.get("RELEASE_WATCH_PROXY", "http://127.0.0.1:10809")
SHIP_MAIL = os.path.expanduser("~/dotfiles/tools/ship-mail/ship-mail.sh")


def _opencode_bin() -> str:
    """Абсолютный путь к opencode: systemd-PATH может не содержать ~/.opencode/bin."""
    found = shutil.which("opencode")
    if found:
        return found
    fallback = os.path.expanduser("~/.opencode/bin/opencode")
    return fallback if os.path.exists(fallback) else "opencode"


def current_version():
    out = subprocess.run([_opencode_bin(), "--version"], capture_output=True,
                         text=True, timeout=30)
    m = re.search(r"(\d+\.\d+\.\d+)", out.stdout or "")
    return m.group(1) if m else None


def fetch_latest():
    """Последний релиз апстрима: (tag, body). Прямо, затем через прокси.

    /releases/latest НЕ годится: эндпоинт отдаёт v1.19.5, хотя v2.2.5
    опубликован (поле latest у апстрима указывает не на максимум semver).
    Беру список релизов и выбираю максимум по semver среди не-draft.
    Источник = то же, что окно «What's new» в TUI (сверено владельцем
    2026-10-31 на 2.2.5 — текст идентичен)."""
    url = f"https://api.github.com/repos/{REPO}/releases?per_page=20"
    last_err = None
    for proxies in (None, {"https": HTTP_PROXY, "http": HTTP_PROXY}):
        try:
            handlers = []
            if proxies:
                handlers.append(urllib.request.ProxyHandler(proxies))
            opener = urllib.request.build_opener(*handlers)
            req = urllib.request.Request(url, headers={
                "User-Agent": "release-watch/1.0 (ship)",
                "Accept": "application/vnd.github+json"})
            with opener.open(req, timeout=30) as r:
                rels = json.loads(r.read().decode("utf-8"))
            best = None
            for rel in rels:
                if rel.get("draft"):
                    continue
                t = (rel.get("tag_name") or "").lstrip("v")
                if not re.match(r"^\d+(\.\d+)*$", t):
                    continue
                key = tuple(int(x) for x in t.split("."))
                if best is None or key > best[0]:
                    best = (key, t, rel.get("body") or "")
            if not best:
                raise RuntimeError("в списке релизов нет semver-тегов")
            return best[1], best[2]
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    raise RuntimeError(f"GitHub API недоступен (прямо и через прокси): "
                       f"{last_err}")


def ver_tuple(v):
    parts = re.findall(r"\d+", v or "")
    return tuple(int(x) for x in parts[:4]) if parts else (0,)


def load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {}


def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    st["last_checked"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1, ensure_ascii=False)
        f.write("\n")


def send_letter(tag, body, installed):
    letter = (
        f"# Новый релиз OpenCode {tag} (установлена {installed or '?'}).\n\n"
        f"Источник: github.com/{REPO}/releases/tag/{tag}\n\n"
        "## Слой 1 — как есть (release notes апстрима)\n\n"
        f"{body.strip()}\n\n"
        "---\n"
        "Дальше по протоколу: Слой 2 (предложения Мастерской — как применить\n"
        "в Корабле) готовит Мастерская при обработке этого письма; Слой 3 —\n"
        "предложения владельца + проверка пригодности (Лаба) + внедрение\n"
        "(ИЦ/ЦУ). Владельцу — короткое резюме человеческим языком.\n")
    path = "/tmp/opencode/release-watch-letter.md"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(letter)
    to = os.environ.get("RELEASE_WATCH_TO",
                        "ses_eda56e1d3ffeyC6AIk1mwgxw1L")  # Мастерская
    r = subprocess.run(
        [SHIP_MAIL, "send", "--to", to,
         "--from", to,
         "--title", f"OpenCode {tag}: релиз — фичи на апрув (3 слоя)",
         "--ref", f"opencode-release-{tag}",
         "--file", path],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or "DELIVERED" not in (r.stdout or ""):
        print(f"release-watch: письмо не доставлено: "
              f"{(r.stderr or r.stdout or '').strip()[:200]}", file=sys.stderr)
        return False
    print(f"release-watch: письмо о {tag} доставлено в ящик Мастерской")
    return True


def main():
    installed = current_version()
    try:
        tag, body = fetch_latest()
    except RuntimeError as e:
        print(str(e)[:300], file=sys.stderr)
        return 2

    latest = tag.lstrip("v")
    st = load_state()
    reported = st.get("last_reported", "")

    # Новый релиз = апстрим новее установленной И не отчитан ранее.
    if ver_tuple(latest) > ver_tuple(installed or "0") and latest != reported:
        ok = send_letter(tag, body, installed)
        if ok:
            st["last_reported"] = latest
            st["installed_at_report"] = installed
            save_state(st)
            return 1
        return 2

    st.setdefault("last_reported", latest)
    save_state(st)
    print(f"release-watch: нового нет (upstream {latest}, "
          f"installed {installed})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
