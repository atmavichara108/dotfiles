#!/usr/bin/env python3
"""captain-panel-media-fetch — резервная загрузка медиа пульта через MTProto.

Bot API ограничивает скачивание ~20 МБ. Большие видео пульта качаем этим
скриптом через профиль portal (сессия Maya). Read-only в части чата: только
одно сообщение по ID. Секреты берутся из env профиля и не печатаются.
"""
import argparse
import os
import sys

os.environ["TG_PROFILE"] = "portal"  # до импорта ядра профиля

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tg_profile  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="captain-panel media fetch")
    ap.add_argument("--chat", required=True, help="ID группы Капитанский портал")
    ap.add_argument("--message-id", type=int, required=True)
    ap.add_argument("--out", required=True, help="путь для сохранения файла")
    ap.add_argument("--expect-from", default="Atma_Vichara108")
    args = ap.parse_args()

    env = tg_profile.load_env(tg_profile.paths()[0])
    api_id = env.get("TG_API_ID", "")
    api_hash = env.get("TG_API_HASH", "")
    group = args.chat or env.get(tg_profile.profile()["group_key"], "")
    proxy = tg_profile.parse_proxy(env.get("TG_PROXY", ""))
    if not api_id or not api_hash or not group:
        sys.exit("captain-panel-media-fetch: нет TG_API_ID/TG_API_HASH/группы")
    session = tg_profile.paths()[1]

    import asyncio
    from telethon import TelegramClient

    async def run():
        async with TelegramClient(session, int(api_id), api_hash,
                                  proxy=proxy) as client:
            ent = await client.get_entity(int(group))
            msg = await client.get_messages(ent, ids=args.message_id)
            if not msg:
                sys.exit("сообщение не найдено")
            sender = ""
            try:
                s = await msg.get_sender()
                sender = getattr(s, "username", "") or ""
            except Exception:  # noqa: BLE001
                sender = ""
            if args.expect_from and sender != args.expect_from:
                sys.exit(f"отправитель не владелец: {sender or '—'}")
            if not msg.media:
                sys.exit("в сообщении нет медиа")
            path = await client.download_media(msg, file=args.out)
            if not path:
                sys.exit("download_media вернул пусто")
            print(path)

    asyncio.run(run())


if __name__ == "__main__":
    main()
