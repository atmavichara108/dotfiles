#!/usr/bin/env python3
"""tg-login — первичный/повторный логин user-сессии моста (профиль SSA по
умолчанию; TG_PROFILE=dv — кабинет dv-hub). Интерактивно, ВЛАДЕЛЬЦЕМ.

Запуск ВЛАДЕЛЬЦЕМ в своём терминале (агент stdin не имеет):
  python3 tg-login.py
Спросит телефон (+7...), затем код из Telegram, затем пароль 2FA (если включён).
Сессия пишется в session-путь профиля. Ничего не отправляет.
Код из Telegram вводит владелец — НЕ агент.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tg_profile  # noqa: E402

_PROFILE = tg_profile.profile()
ENV_FILE, SESSION, _STATE_DIR = tg_profile.paths()


def load_env(path):
    """Оставлено для совместимости (см. tg_profile.load_env)."""
    return tg_profile.load_env(path)


async def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print("tg-login [--help]: интерактивный логин владельца, сеть — "
              "только auth; ничего не читает и не отправляет.")
        return
    stray = [a for a in sys.argv[1:] if a.startswith("-")]
    if stray:
        sys.exit(f"tg-login: неизвестные аргументы {stray} — отказ "
                 "(принимается только --help)")
    env = load_env(ENV_FILE)
    if not env.get("TG_API_ID") or not env.get("TG_API_HASH"):
        sys.exit("tg-login: заполни TG_API_ID/TG_API_HASH в " + ENV_FILE)
    from telethon import TelegramClient
    proxy = tg_profile.parse_proxy(env.get("TG_PROXY", ""))
    if proxy is not None:
        try:
            import python_socks  # noqa: F401
        except ImportError:
            sys.exit("tg-login: нужен python-socks "
                     "(pip install --user --break-system-packages 'python-socks[asyncio]')")
    async with TelegramClient(SESSION, int(env["TG_API_ID"]),
                              env["TG_API_HASH"], proxy=proxy) as client:
        me = await client.get_me()
        print(f"tg-login: ok, вошёл как @{me.username} id={me.id}")


if __name__ == "__main__":
    asyncio.run(main())
