#!/usr/bin/env python3
"""tg-read — чтение новых сообщений ОДНОГО топика рабочей группы (профиль SSA
по умолчанию; TG_PROFILE=dv — кабинет dv-hub, топик 1399).

Read-only, ничего не отправляет. Fail-closed: живое чтение ТОЛЬКО с explicit
--topic ID; без топика, с неизвестным топиком или неизвестным флагом — отказ,
никакого group-wide read.

Использование:
  python3 tg-read.py --help
  python3 tg-read.py --topic ID [--limit N] [--since-id ID] [--no-save]
Вывод: JSON-строки {id, topic, date, from, text} в stdout.
Маркер последнего прочитанного — per-topic: <state-профиля>/last_id_<topic>
(--since-id перекрывает маркер разово; --no-save не двигает маркер).

Зависимость: telethon (системно). Секреты — только env-файл профиля.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tg_profile  # noqa: E402

_PROFILE = tg_profile.profile()
ENV_FILE, SESSION, STATE_DIR = tg_profile.paths()

USAGE = """tg-read --topic ID [--limit N] [--since-id ID] [--no-save]
  --topic ID   ID форумного топика (обязателен; без него чтения нет)
  --limit N    сколько сообщений (default 20)
  --since-id ID  читать только новее ID (разово, маркер не трогает)
  --no-save    не двигать per-topic маркер last_id_<topic>
Вывод: JSON {id, topic, date, from, text}."""


async def main():
    argv = sys.argv[1:]
    if "--help" in argv or "-h" in argv:
        print(USAGE)  # безвредно: до сети, env и маркеров не доходим
        return
    limit = 20
    since = None
    save = True
    topic = None
    known_vals = set()
    if "--limit" in argv:
        i = argv.index("--limit")
        limit = int(argv[i + 1])
        known_vals.update([argv[i + 1]])
    if "--since-id" in argv:
        i = argv.index("--since-id")
        since = int(argv[i + 1])
        known_vals.update([argv[i + 1]])
    if "--topic" in argv:
        i = argv.index("--topic")
        topic = int(argv[i + 1])
        known_vals.update([argv[i + 1]])
    if "--no-save" in argv:
        save = False
    # строже: любой токен вне известных флагов/значений — отказ
    allowed = {"--limit", "--since-id", "--topic", "--no-save"} | known_vals
    stray = [a for a in argv if a not in allowed]
    if stray:
        sys.exit(f"tg-read: неизвестные аргументы {stray} — отказ (см. --help)")
    if topic is None:
        sys.exit("tg-read: нет --topic ID — живое чтение запрещено "
                 "(fail-closed, group-wide read отключён; см. --help)")
    # whitelist чтения профиля (dv: только свой кабинет) — отказ ДО сети
    read_scope = _PROFILE.get("read_topics")
    if read_scope is not None and topic not in read_scope:
        tg_profile.journal_append({"action": "read-refused", "topic": topic,
                                   "reason": "outside-read-scope"})
        sys.exit(f"tg-read: профиль {_PROFILE['name']}: чтение только топиков "
                 f"{sorted(read_scope)} — отказ ДО сети (см. --help)")
    last_file = os.path.join(STATE_DIR, f"last_id_{topic}")
    if since is None and os.path.exists(last_file):
        with open(last_file) as f:
            since = int((f.read().strip() or "0"))

    env = tg_profile.load_env(ENV_FILE)
    api_id = env.get("TG_API_ID", "")
    api_hash = env.get("TG_API_HASH", "")
    group = env.get(_PROFILE["group_key"], "")
    proxy = tg_profile.parse_proxy(env.get("TG_PROXY", ""))
    if not api_id or not api_hash or not group:
        sys.exit(f"tg-read: заполни TG_API_ID/TG_API_HASH/{_PROFILE['group_key']} в " + ENV_FILE)
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
        ent = await client.get_entity(int(group))
        topics = await _topic_ids(client, ent)
        if topic not in topics:
            sys.exit(f"tg-read: топика {topic} нет в группе "
                     f"(есть: {sorted(topics)}) — отказ")
        msgs = await client.get_messages(ent, limit=limit, min_id=since or 0,
                                         reply_to=topic)
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
                        "topic": topic,
                        "date": m.date.isoformat() if m.date else "",
                        "from": sender,
                        "text": m.text or ""})
        for row in out:
            print(json.dumps(row, ensure_ascii=False))
        if save and out:
            with open(last_file, "w") as f:
                f.write(str(out[-1]["id"]))
        sys.stderr.write(f"tg-read: topic={topic} новых={len(out)} "
                         f"(since={since or 0})\n")


async def _topic_ids(client, entity):
    """ID существующих топиков (только метаданные заголовков, без текстов)."""
    from telethon.tl.functions.messages import GetForumTopicsRequest
    r = await client(GetForumTopicsRequest(
        peer=entity, offset_date=None, offset_id=0, offset_topic=0, limit=100))
    return {t.id for t in r.topics}


if __name__ == "__main__":
    asyncio.run(main())
