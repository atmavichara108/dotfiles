#!/usr/bin/env python3
"""tg-send — отправка сообщения в рабочую группу SSA от имени владельца.

Безопасность:
  - получатель ТОЛЬКО SSA_GROUP_ID из env (whitelist, переопределения нет);
  - секреты только из ~/.config/ssa-tg/tg.env, никогда из аргументов/репо;
  - запуск: python3 tg-send.py [--dry-run] [--file TEXTFILE] [ТЕКСТ ...]
    (exec-бит ставит владелец: chmod +x — вне зоны агента).

Зависимость: telethon (системно, ставит владелец: pip install --user telethon).
"""
import os
import sys

ENV_FILE = os.path.expanduser("~/.config/ssa-tg/tg.env")
SESSION = os.path.expanduser("~/.local/state/ssa-tg/ssa.session")


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


def main(argv):
    dry = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]
    text = ""
    topic = None
    if "--topic" in argv:
        i = argv.index("--topic")
        topic = int(argv[i + 1])
        argv = [a for a in argv if a not in ("--topic", str(topic))]
    if "--file" in argv:
        i = argv.index("--file")
        with open(argv[i + 1], encoding="utf-8") as f:
            text = f.read()
    elif argv:
        text = " ".join(argv)
    else:
        text = sys.stdin.read()
    text = text.strip()
    if not text:
        sys.exit("tg-send: пустой текст — нечего отправлять")

    env = load_env(ENV_FILE)
    api_id = env.get("TG_API_ID", "")
    api_hash = env.get("TG_API_HASH", "")
    group = env.get("SSA_GROUP_ID", "")
    proxy = parse_proxy(env.get("TG_PROXY", ""))
    if not api_id or not api_hash or not group:
        sys.exit("tg-send: заполни TG_API_ID/TG_API_HASH/SSA_GROUP_ID в " + ENV_FILE)
    try:
        from telethon import TelegramClient
    except ImportError:
        sys.exit("tg-send: нет telethon (владелец ставит: pip install --user telethon)")
    try:
        import python_socks  # noqa: F401  (нужен telethon для TG_PROXY)
    except ImportError:
        if proxy is not None:
            sys.exit("tg-send: задан TG_PROXY, но нет python-socks "
                     "(владелец ставит: pip install --user 'python-socks[asyncio]')")

    if dry:
        print(f"dry-run -> chat {group}: {text[:120]}")
        return

    import asyncio

    async def send():
        async with TelegramClient(SESSION, int(api_id), api_hash,
                                  proxy=proxy) as client:
            me = await client.get_me()
            sys.stderr.write(f"tg-send: как {me.username or me.id} -> {group}"
                             + (f" topic={topic}" if topic else "") + "\n")
            msg = await client.send_message(int(group), text, reply_to=topic)
            print(f"tg-send: ok id={msg.id}")

    asyncio.run(send())


if __name__ == "__main__":
    main(sys.argv[1:])
