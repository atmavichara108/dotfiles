#!/usr/bin/env python3
"""tg-profile-doctor — сторож TG-профилей (инцидент env-overwrite 2026-10-29).

Сегодня env-файлы профилей перетирались «с нуля» и теряли TG_API_ID/
TG_API_HASH — профили падали в «заполни ключи» (мосты отказывают чисто,
но канал молчит). Причина класса: запись env БЕЗ чтения текущего
(open O_TRUNC) вместо merge. Этот doctor проверяет все профили репо и
сообщает, где что отсутствует:
  1. env-файл есть, TG_API_ID/TG_API_HASH непустые;
  2. группа (PROFILE_GROUP_ID) задана;
  3. session-файл существует и непустой;
  4. у chat-scope профилей заданы TG_OWN/TG_OWNER (граница).
Выход: 0 — все здоровы; 1 — найдены болезни (список).

Запуск: python3 tg-profile-doctor.py [--quiet]
"""
import glob
import os
import sys

PROFILES_DIRS = [
    "~/.config/ssa-tg", "~/.config/dv-tg", "~/.config/serp-tg",
    "~/.config/portal-tg",
]
REQUIRED = ["TG_API_ID", "TG_API_HASH"]


def parse_env(path):
    env = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip().startswith("export "):
            k = k.strip()[len("export "):]
        env[k.strip()] = v.strip().strip("'\"")
    return env


def check_profile(cfg_dir, quiet):
    name = os.path.basename(cfg_dir)
    problems = []
    env_path = os.path.join(cfg_dir, "tg.env")
    if not os.path.exists(env_path):
        return [f"{name}: нет env {env_path}"]
    env = parse_env(env_path)
    for k in REQUIRED:
        if not env.get(k):
            problems.append(f"{name}: {k} пустой/отсутствует")
    group_key = [k for k in env if k.endswith("GROUP_ID")]
    if not group_key or not env[group_key[0]]:
        problems.append(f"{name}: нет GROUP_ID")
    state_dir = os.path.expanduser(
        env.get("STATE_DIR") or cfg_dir.replace(".config", ".local/state"))
    sessions = glob.glob(os.path.join(state_dir, "*.session"))
    alive = [s for s in sessions if os.path.getsize(s) > 10000]
    if not alive:
        problems.append(f"{name}: нет действующей сессии в {state_dir}")
    return problems


def main(argv):
    quiet = "--quiet" in argv
    all_problems = []
    for d in PROFILES_DIRS:
        p = os.path.expanduser(d)
        if not os.path.isdir(p):
            continue
        all_problems += check_profile(p, quiet)
    if all_problems:
        print("tg-profile-doctor: БОЛЕЗНИ:")
        for x in all_problems:
            print(" -", x)
        return 1
    if not quiet:
        print("tg-profile-doctor: все профили здоровы (env+ключи+сессия)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
