#!/usr/bin/env python3
"""tg-login — первичный/повторный логин user-сессии SSA-моста (интерактивно).

Запуск ВЛАДЕЛЬЦЕМ в своём терминале (агент stdin не имеет):
  python3 tg-login.py
Спросит телефон (+7...), затем код из Telegram, затем пароль 2FA (если включён).
Сессия пишется в ~/.local/state/ssa-tg/ssa.session. Ничего не отправляет.
"""
import asyncio
import os
import sys


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
    url = (url or "").strip()
    if not url:
        return None
    scheme, _, rest = url.partition("://")
    host, _, port = rest.partition(":")
    return (scheme or "socks5", host, int(port or "1080"))


ENV_FILE = os.path.expanduser("~/.config/ssa-tg/tg.env")
SESSION = os.path.expanduser("~/.local/state/ssa-tg/ssa.session")


async def main():
    env = load_env(ENV_FILE)
    if not env.get("TG_API_ID") or not env.get("TG_API_HASH"):
        sys.exit("tg-login: заполни TG_API_ID/TG_API_HASH в " + ENV_FILE)
    from telethon import TelegramClient
    proxy = parse_proxy(env.get("TG_PROXY", ""))
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
