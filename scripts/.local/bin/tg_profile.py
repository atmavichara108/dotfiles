#!/usr/bin/env python3
"""tg_profile — профили TG-мостов (ssa по умолчанию, dv — второй профиль).

Один механизм вместо размножения файлов: переменная окружения TG_PROFILE
выбирает профиль; без неё поведение побайтово как у SSA-профиля (мандат
dv-tg-gateway 2026-10-24, DoD: SSA-профиль не изменён).

Профили:
  ssa — env ~/.config/ssa-tg/tg.env, session ssa.session, группа SSA_GROUP_ID,
        живая отправка только в топик 33; чтение любого явного топика (как
        раньше); журнал ведает tg-guard (guard-journal.jsonl).
  dv  — env ~/.config/dv-tg/tg.env (заполняет владелец), session dv.session,
        группа DV_GROUP_ID (кабинет топика 1399); отправка и чтение — только
        топик 1399, отказ ДО сети; журнал ~/.local/state/dv-tg/journal.jsonl
        (метаданные + text_preview <= 200, без тел и секретов).

Секретов здесь нет и быть не может: профиль знает только ПУТИ и ID.
"""
import json
import os
import sys
import time

PROFILES = {
    "ssa": {
        "name": "ssa",
        "env_file": "~/.config/ssa-tg/tg.env",
        "session": "~/.local/state/ssa-tg/ssa.session",
        "state_dir": "~/.local/state/ssa-tg",
        "group_key": "SSA_GROUP_ID",
        "allowed_topics": {33},
        "read_topics": None,          # None = как раньше: любой явный топик
        "group_default": "",          # env обязателен (как раньше)
        "journal": None,              # журнал SSA — зона tg-guard
    },
    "dv": {
        "name": "dv",
        "env_file": "~/.config/dv-tg/tg.env",
        "session": "~/.local/state/dv-tg/dv.session",
        "state_dir": "~/.local/state/dv-tg",
        "group_key": "DV_GROUP_ID",
        "allowed_topics": {1399},
        "read_topics": {1399},
        "group_default": "-1003818507530",  # только для dry-run до создания env
        "journal": "journal.jsonl",
    },
    "serp": {
        "name": "serp",
        "env_file": "~/.config/serp-tg/tg.env",
        "session": "~/.local/state/serp-tg/serp.session",
        "state_dir": "~/.local/state/serp-tg",
        "group_key": "SERP_GROUP_ID",
        "allowed_topics": {186},
        "read_topics": {186},
        # тот же чат, что у SSA (t.me/c/4481532605 → -1004481532605),
        # топик 186 — сервисный центр SERPlux (мандат ЦУ 2026-10-29)
        "group_default": "-1004481532605",
        "journal": "journal.jsonl",
    },
    "portal": {
        "name": "portal",
        "env_file": "~/.config/portal-tg/tg.env",
        "session": "~/.local/state/portal-tg/portal.session",
        "state_dir": "~/.local/state/portal-tg",
        "group_key": "PORTAL_GROUP_ID",
        # Капитанский портал: весь чат без форум-топиков (мандат ЦУ
        # portal-profile-mandate 2026-10-29). scope = группа, не топик.
        "chat_scope": True,
        "allowed_topics": None,
        "read_topics": None,
        "group_default": "-1003786610623",
        "journal": "journal.jsonl",
    },
}

PREVIEW_MAX = 200


def die(msg):
    sys.exit(f"tg-profile: {msg}")


def get_profile():
    """Имя профиля из TG_PROFILE (умолчание ssa). Неизвестное — отказ."""
    name = (os.environ.get("TG_PROFILE") or "ssa").strip()
    if name not in PROFILES:
        die(f"неизвестный профиль {name!r} (есть: {sorted(PROFILES)}) — отказ")
    return name


def profile(name=None):
    return PROFILES[name or get_profile()]


def paths(p=None):
    """Раскрытые пути профиля: (env_file, session, state_dir)."""
    p = p or profile()
    return (os.path.expanduser(p["env_file"]),
            os.path.expanduser(p["session"]),
            os.path.expanduser(p["state_dir"]))


def journal_path(p=None):
    p = p or profile()
    if not p.get("journal"):
        return None
    return os.path.join(os.path.expanduser(p["state_dir"]), p["journal"])


def preview(text, limit=PREVIEW_MAX):
    """Обрезанный превью-текст для журнала (полное тело не пишем)."""
    t = (text or "").replace("\n", " ")
    return t[:limit]


def journal_append(row, p=None):
    """Дописать строку-мету в журнал профиля (только если профиль с журналом).

    Пишем только меты: время, профиль, действие, топик, счётчики, превью.
    Секреты не проходят через журнал по построению.
    """
    path = journal_path(p)
    if not path:
        return None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        rec = {"ts": int(time.time()), "profile": (p or profile()).get("name", get_profile()),
               **row}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return path
    except Exception as e:  # noqa: BLE001 — журнал вспомогательный, не роняем мост
        sys.stderr.write(f"tg-profile: WARNING: журнал не записан ({e!r})\n")
        return None


def load_env(path):
    env = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    return env


def parse_proxy(url):
    """socks5://host:port -> кортеж для telethon. Пусто -> None (прямое)."""
    url = (url or "").strip()
    if not url:
        return None
    scheme, _, rest = url.partition("://")
    host, _, port = rest.partition(":")
    return (scheme or "socks5", host, int(port or "1080"))
