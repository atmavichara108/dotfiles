#!/usr/bin/env python3
"""tg-read — чтение новых сообщений рабочей группы SSA (read-only, ничего не отправляет).

Использование:
  python3 tg-read.py [--limit N] [--since-id ID] [--no-save]
Вывод: JSON-строки {id, date, from, text} в stdout.
Маркер последнего прочитанного хранится в ~/.local/state/ssa-tg/last_id
(--since-id перекрывает маркер разово; --no-save не двигает маркер).

Зависимость: telethon (системно). Секреты — только ~/.config/ssa-tg/tg.env.
"""
import asyncio
import json
import os
import sys

ENV_FILE = os.path.expanduser("~/.config/ssa-tg/tg.env")
SESSION = os.path.expanduser("~/.local/state/ssa-tg/ssa.session")
LAST_ID = os.path.expanduser("~/.local/state/ssa-tg/last_id")


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


async def main():
    argv = sys.argv[1:]
    limit = 20
    since = None
    save = True
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    if "--since-id" in argv:
        since = int(argv[argv.index("--since-id") + 1])
    if "--no-save" in argv:
        save = False
    if since is None and os.path.exists(LAST_ID):
        with open(LAST_ID) as f:
            since = int((f.read().strip() or "0"))

    env = load_env(ENV_FILE)
    api_id = env.get("TG_API_ID", "")
    api_hash = env.get("TG_API_HASH", "")
    group = env.get("SSA_GROUP_ID", "")
    proxy = parse_proxy(env.get("TG_PROXY", ""))
    if not api_id or not api_hash or not group:
        sys.exit("tg-read: заполни TG_API_ID/TG_API_HASH/SSA_GROUP_ID в " + ENV_FILE)
    try:
        from telethon import TelegramClient
    except ImportError:
        sys.exit("tg-read: нет telethon (владелец ставит: pip install --user telethon)")
    try:
        import python_socks  # noqa: F401  (нужен telethon для TG_PROXY)
    except ImportError:
        if proxy is not None:
            sys.exit("tg-read: задан TG_PROXY, но нет python-socks "
                     "(владелец ставит: pip install --user 'python-socks[asyncio]')")

    async with TelegramClient(SESSION, int(api_id), api_hash,
                              proxy=proxy) as client:
        msgs = await client.get_messages(int(group), limit=limit, min_id=since or 0)
        out = []
        for m in sorted(msgs, key=lambda x: x.id):
            sender = ""
            try:
                s = await m.get_sender()
                sender = (getattr(s, "username", "") or
                          f"{getattr(s, 'first_name', '')} {getattr(s, 'last_name', '')}".strip()
                          or str(getattr(s, "id", "")))
            except Exception:  # noqa: BLE001
                sender = "?"
            out.append({"id": m.id,
                        "date": m.date.isoformat() if m.date else "",
                        "from": sender,
                        "text": m.text or ""})
        for row in out:
            print(json.dumps(row, ensure_ascii=False))
        if save and out:
            with open(LAST_ID, "w") as f:
                f.write(str(out[-1]["id"]))
        sys.stderr.write(f"tg-read: {len(out)} новых (since={since or 0})\n")


if __name__ == "__main__":
    asyncio.run(main())
