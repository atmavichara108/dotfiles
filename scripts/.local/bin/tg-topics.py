#!/usr/bin/env python3
"""tg-topics — управление форум-топиками чата (создание/список/переименование).

Профили: TG_PROFILE=portal (по умолчанию — портал), обёртка portal-tg-topics.
Только для профилей, чей аккаунт — админ чата (Maya подтверждён:
ChannelParticipantAdmin в «Капитанском портале»). Без прав телеграм
откажет — инструмент не имитирует успех.

Использование:
  python3 tg-topics.py list
  python3 tg-topics.py create "<название>"
  python3 tg-topics.py rename <topic_id> "<новое название>"

Вывод идемпотентен и машинно-читаем (JSON для create).
Секреты — только env профиля; ничего не пишет в репозиторий.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tg_profile  # noqa: E402

ENV_FILE, SESSION, STATE_DIR = tg_profile.paths()

USAGE = """tg-topics <list|create|rename> ...
  list                      форум-топики чата: id + title
  create "<название>"        создать топик (нужны права админа)
  rename <topic_id> "<...>"  переименовать топик
Профиль: TG_PROFILE=portal (обёртка portal-tg-topics)."""


async def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("--help", "-h"):
        print(USAGE)
        return
    cmd = argv[0]
    env = tg_profile.load_env(ENV_FILE)
    group = env.get(tg_profile.profile()["group_key"], "")
    if not group:
        sys.exit("tg-topics: нет группы в env — заполни "
                 + tg_profile.profile()["group_key"] + " в " + ENV_FILE)
    if not os.path.exists(SESSION) or os.path.getsize(SESSION) == 0:
        sys.exit("tg-topics: нет действующей сессии — сначала вход: "
                 "tg-login.py (профиль " + tg_profile.profile()["name"] + ")")

    from telethon import TelegramClient
    from telethon.tl.functions.messages import (
        CreateForumTopicRequest, EditForumTopicRequest,
        GetForumTopicsRequest)

    async with TelegramClient(SESSION, int(env["TG_API_ID"]),
                              env["TG_API_HASH"],
                              proxy=tg_profile.parse_proxy(
                                  env.get("TG_PROXY", ""))) as client:
        ent = await client.get_entity(int(group))

        async def _topics():
            r = await client(GetForumTopicsRequest(
                peer=ent, offset_date=None, offset_id=0, offset_topic=0,
                limit=100))
            return [{"id": t.id, "title": t.title} for t in r.topics]

        if cmd == "list":
            for t in await _topics():
                print(json.dumps(t, ensure_ascii=False))
            return

        if cmd == "create":
            if len(argv) < 2 or not argv[1].strip():
                sys.exit("tg-topics: create требует название")
            try:
                res = await client(CreateForumTopicRequest(
                    peer=ent, title=argv[1].strip()))
            except Exception as e:  # noqa: BLE001
                sys.exit("tg-topics: создание не удалось ("
                         + type(e).__name__ + "): " + str(e)[:200]
                         + " — вероятно, нет прав админа в чате")
            print(json.dumps({"created": True,
                              "id": res.message.id if hasattr(res, "message")
                              else None,
                              "title": argv[1].strip()},
                             ensure_ascii=False))
            return

        if cmd == "rename":
            if len(argv) < 3:
                sys.exit("tg-topics: rename требует topic_id и название")
            try:
                await client(EditForumTopicRequest(
                    peer=ent, topic_id=int(argv[1]), title=argv[2].strip()))
            except Exception as e:  # noqa: BLE001
                sys.exit("tg-topics: переименование не удалось ("
                         + type(e).__name__ + "): " + str(e)[:200])
            print(json.dumps({"renamed": True, "id": int(argv[1]),
                              "title": argv[2].strip()}, ensure_ascii=False))
            return

        sys.exit("tg-topics: неизвестная команда (см. --help)")


if __name__ == "__main__":
    asyncio.run(main())
