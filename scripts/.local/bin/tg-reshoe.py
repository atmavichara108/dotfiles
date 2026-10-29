#!/usr/bin/env python3
"""tg-reshoe — переобувка профилей TG-мостов на единый sender-аккаунт (Maya).

Мандат: слово владельца 2026-10-29 («сменить акк с которого пишут агенты на
@AllIsMaya ... переобуть агентов»). Мосты (tg-send/tg-read и стражи профилей)
писали с личного аккаунта; Maya живёт в recruiting-контура (env+сессия).

Что делает для каждого профиля (ssa/dv/serp/portal):
  1. env профиля: значения TG_API_ID/TG_API_HASH/TG_PROXY заменяются на
     Maya-значения; групповые ключи профиля (SSA_GROUP_ID/…) сохраняются.
  2. сессия профиля: Maya-сессия копируется на путь базовой сессии;
     старая сессия и лишние *-session копии переезжают в backup-каталог
     (не удаляются — откат возможен; демоны до рестарта держат старые fd).
  3. секреты никогда не печатаются: сверки — только длина/совпадение.

Режим: по умолчанию dry-run (план без записи). Запись — --apply.
Значения берутся из maya-пары (recruiting-hr), репо/журналы их не видят.
"""
import glob
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tg_profile  # noqa: E402

MAYA_ENV = "~/Projects/recruiting-hr/data-private/tg.env"
MAYA_SESSION = "~/Projects/recruiting-hr/data-private/tg_user.session"
TG_KEYS = ("TG_API_ID", "TG_API_HASH", "TG_PROXY")


def load_env(path):
    """env-файл -> dict; поддерживает префикс 'export ' (recruiting-формат)."""
    env = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:]
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    return env


def render_env(env, order):
    lines = []
    for k in order:
        if k in env:
            lines.append(f"{k}={env[k]}")
    return "\n".join(lines) + "\n"


def reshoe(name, maya, backup_dir, apply_):
    p = tg_profile.PROFILES[name]
    env_path, session, state = tg_profile.paths(p)
    actions = []

    old = load_env(env_path) if os.path.exists(env_path) else {}
    order = [k for k in old if k not in TG_KEYS] + list(TG_KEYS)
    new = dict(old)
    changed = []
    for k in TG_KEYS:
        want = maya.get(k, "")
        if want and new.get(k) != want:
            new[k] = want
            changed.append(k)
    if changed:
        actions.append(f"env: заменить {','.join(changed)} (файл {env_path})")
        if apply_:
            tmp = env_path + ".tmp-reshoe"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(render_env(new, order))
            os.replace(tmp, env_path)

    if not os.path.exists(MAYA_SESSION):
        actions.append(f"сессия: Maya-сессия не найдена ({MAYA_SESSION}) — стоп")
        return actions, True

    if os.path.exists(session):
        # если базовая сессия уже maya-копия — не трогаем
        same = os.path.getsize(session) == os.path.getsize(MAYA_SESSION)
        if not same:
            dst = os.path.join(backup_dir, f"{name}__" + os.path.basename(session))
            actions.append(f"сессия: старую -> backup ({os.path.basename(session)})")
            if apply_:
                shutil.move(session, dst)
        else:
            actions.append("сессия: уже maya-размера (возможно, переобута) — сверка whoami обязательна")
    if not os.path.exists(session):
        actions.append(f"сессия: копия Maya -> {session}")
        if apply_:
            os.makedirs(os.path.dirname(session), exist_ok=True)
            shutil.copy2(MAYA_SESSION, session)

    if apply_ and os.path.exists(session):
        # финальная синхронизация: если старую не двигали (тот же размер),
        # перезаписываем maya-копией поверх (тот же аккаунт под тем же именем)
        if os.path.getmtime(session) < os.path.getmtime(MAYA_SESSION):
            shutil.copy2(MAYA_SESSION, session)

    for s in sorted(glob.glob(os.path.join(state, "*.session"))):
        if os.path.basename(s) == os.path.basename(session):
            continue
        actions.append(f"копия: {os.path.basename(s)} -> backup (страж пересоздаст после рестарта)")
        if apply_:
            shutil.move(s, os.path.join(backup_dir, f"{name}__" + os.path.basename(s)))
    return actions, False


def main():
    args = sys.argv[1:]
    apply_ = "--apply" in args
    names = [a for a in args if not a.startswith("--")] or sorted(tg_profile.PROFILES)
    global MAYA_SESSION
    MAYA_SESSION = os.path.expanduser(MAYA_SESSION)
    maya = load_env(os.path.expanduser(MAYA_ENV))
    missing = [k for k in TG_KEYS[:2] if not maya.get(k)]
    if missing:
        sys.exit(f"tg-reshoe: в maya-env нет {missing} — стоп")
    stamp = time.strftime("%Y%m%dT%H%M%S")
    backup_dir = os.path.expanduser(f"~/.local/state/tg-reshoe-backup-{stamp}")
    if apply_:
        os.makedirs(backup_dir, exist_ok=True)
    print(f"tg-reshoe: режим {'APPLY' if apply_ else 'DRY-RUN'} | профили: {names}")
    if apply_:
        print(f"tg-reshoe: backup-каталог: {backup_dir}")
    for n in names:
        print(f"== профиль {n}")
        acts, stop = reshoe(n, maya, backup_dir, apply_)
        for a in acts:
            print("   ", a)
        if stop:
            sys.exit(1)
    if not apply_:
        print("tg-reshoe: ничего не записано (dry-run). Запись: tg-reshoe.py --apply")


if __name__ == "__main__":
    main()
