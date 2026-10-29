#!/usr/bin/env python3
"""tg-whoami — кто сейчас является отправителем профиля TG-моста (read-only).

Показывает публичный аккаунт (id/@username/имя), под которым мостики
tg-send/tg-read пишут от профиля. Никаких секретов: только get_me().

Профиль выбирается переменной TG_PROFILE (умолчание ssa, см. tg_profile.py).
Сеть: один авторизованный getMe-запрос. Без сессии/с просроченной — честный
отказ (вход кода — только владелец, не сюда).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tg_profile  # noqa: E402


async def main():
    from telethon import TelegramClient  # локальный импорт: без telethon — честная ошибка

    p = tg_profile.profile()
    env_file, session, _state = tg_profile.paths(p)
    if not os.path.exists(session):
        sys.exit(f"tg-whoami: профиль {p['name']!r}: сессия не найдена ({session})")
    if not os.path.exists(env_file):
        sys.exit(f"tg-whoami: профиль {p['name']!r}: env не найден ({env_file})")
    env = tg_profile.load_env(env_file)
    try:
        api_id = int(env["TG_API_ID"])
        api_hash = env["TG_API_HASH"]
    except (KeyError, ValueError):
        sys.exit(f"tg-whoami: профиль {p['name']!r}: в env нет TG_API_ID/TG_API_HASH")
    proxy = tg_profile.parse_proxy(env.get("TG_PROXY", ""))
    async with TelegramClient(session, api_id, api_hash, proxy=proxy) as client:
        me = await client.get_me()
        user = getattr(me, "username", None)
        name = getattr(me, "first_name", "") or ""
        print(f"profile={p['name']} id={me.id} @{'username=' + user if user else '(без @)'} name={name!r}")


if __name__ == "__main__":
    asyncio.run(main())
