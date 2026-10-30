#!/usr/bin/env python3
"""tg-edit — fail-closed редактирование СВОИХ существующих сообщений в топике.

Рамки текущей задачи (owner scope, 2026-10-14): topic ровно 33 («Тэсты»),
message IDs ровно {34, 41, 42}. Никаких новых сообщений (sendMessage нет
в коде вообще), никаких других топиков/чатов.

Двухфазность: сначала проверяются ВСЕ три (своё исходящее + топик 33),
потом применяются ВСЕ. Любой провал проверки — ноль правок, отказ.

Использование:
  python3 tg-edit.py --help
  python3 tg-edit.py --topic 33 --edits edits.json [--dry-run]
edits.json: {"34": "новый текст", "41": "...", "42": "..."} — ключи строго
из разрешённого набора, пустые тексты запрещены (стирания нет).

Зависимость: telethon (системно). Секреты — только ~/.config/ssa-tg/tg.env.
"""
import json
import os
import sys

ENV_FILE = os.path.expanduser("~/.config/ssa-tg/tg.env")
SESSION = os.path.expanduser("~/.local/state/ssa-tg/ssa.session")

ALLOWED_TOPIC = 33
ALLOWED_IDS = {34, 41, 42}
ALLOWED_DELETE_IDS = {41, 42}  # 34 удалять запрещено всегда
ALLOWED_SENDERS = {"atma_vichara108", "allismaya"}  # allow-list topic 33 (слово владельца 2026-10-30: Майя говорит за канал)

USAGE = """tg-edit --topic 33 (--edits edits.json | --delete 41,42) [--dry-run]
  --topic 33        разрешён ровно topic 33 (другое — отказ)
  --edits PATH      JSON {id: новый текст}; id строго из {34, 41, 42};
                    пустой текст запрещён
  --delete IDS      удалить СВОИ сообщения; id строго из {41, 42} через запятую;
                    несовместим с --edits (оба/ничего — отказ)
  --dry-run         только проверка + превью, без edit/delete
Правит/удаляет только свои исходящие (out) сообщения топика 33 владельца
Atma_Vichara108 через edit_message/delete_messages. Новых сообщений
не создаёт (sendMessage в коде нет); mismatch — стоп, fallback на send нет."""


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


def main(argv):
    if "--help" in argv or "-h" in argv:
        print(USAGE)  # безвредно: до env, сети и файла правок не доходим
        return
    dry = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]
    topic = None
    edits_path = None
    delete_ids = None
    known_vals = set()
    if "--topic" in argv:
        i = argv.index("--topic")
        topic = int(argv[i + 1])
        known_vals.add(argv[i + 1])
    if "--edits" in argv:
        i = argv.index("--edits")
        edits_path = argv[i + 1]
        known_vals.add(argv[i + 1])
    if "--delete" in argv:
        i = argv.index("--delete")
        delete_ids = {int(x) for x in argv[i + 1].split(",") if x.strip()}
        known_vals.add(argv[i + 1])
    allowed = {"--topic", "--edits", "--delete"} | known_vals
    stray = [a for a in argv if a not in allowed]
    if stray:
        sys.exit(f"tg-edit: неизвестные аргументы {stray} — отказ (см. --help)")
    if topic is None:
        sys.exit("tg-edit: нет --topic ID — отказ (fail-closed; см. --help)")
    if topic != ALLOWED_TOPIC:
        sys.exit(f"tg-edit: разрешён ровно topic {ALLOWED_TOPIC} — отказ")
    if bool(edits_path) == bool(delete_ids):
        sys.exit("tg-edit: нужен ровно один режим: --edits ЛИБО --delete — отказ")
    if delete_ids is not None:
        if not delete_ids <= ALLOWED_DELETE_IDS:
            sys.exit(f"tg-edit: удалять разрешено только {sorted(ALLOWED_DELETE_IDS)}: "
                     f"{sorted(delete_ids - ALLOWED_DELETE_IDS)} — отказ, ноль удалений")
        edits = {}
    else:
        with open(edits_path, encoding="utf-8") as f:
            edits = json.load(f)
    if delete_ids is not None:
        ids = set(delete_ids)
        edits = {}
    else:
        ids = {int(k) for k in edits}
        if not ids:
            sys.exit("tg-edit: пустой edits-файл — отказ")
    if not ids <= ALLOWED_IDS:
        sys.exit(f"tg-edit: id вне разрешённого набора {sorted(ALLOWED_IDS)}: "
                 f"{sorted(ids - ALLOWED_IDS)} — отказ, ноль правок")
    for k, v in edits.items():
        if not isinstance(v, str) or not v.strip():
            sys.exit(f"tg-edit: пустой/нестроковый текст для id={k} — отказ "
                     "(стирание запрещено)")

    env = load_env(ENV_FILE)
    api_id = env.get("TG_API_ID", "")
    api_hash = env.get("TG_API_HASH", "")
    group = env.get("SSA_GROUP_ID", "")
    proxy = parse_proxy(env.get("TG_PROXY", ""))
    if not api_id or not api_hash or not group:
        sys.exit("tg-edit: заполни TG_API_ID/TG_API_HASH/SSA_GROUP_ID в " + ENV_FILE)
    try:
        from telethon import TelegramClient
    except ImportError:
        sys.exit("tg-edit: нет telethon")
    try:
        import python_socks  # noqa: F401
    except ImportError:
        if proxy is not None:
            sys.exit("tg-edit: задан TG_PROXY, но нет python-socks")

    import asyncio

    async def run():
        async with TelegramClient(SESSION, int(api_id), api_hash,
                                  proxy=proxy) as client:
            me = await client.get_me()
            if (me.username or "").lower() not in ALLOWED_SENDERS:
                sys.exit(f"tg-edit: сессия не владельца "
                         f"(ожидался один из {sorted(ALLOWED_SENDERS)}) — отказ")
            ent = await client.get_entity(int(group))
            if not await _topic_exists(client, ent, topic):
                sys.exit(f"tg-edit: топика {topic} нет в группе — отказ")
            # Фаза 1: проверить ВСЕ до единой операции.
            targets = []
            for mid in sorted(ids):
                m = await client.get_messages(ent, ids=mid)
                if m is None:
                    sys.exit(f"tg-edit: сообщение id={mid} не найдено — "
                             "отказ, ноль операций")
                if not getattr(m, "out", False):
                    sys.exit(f"tg-edit: id={mid} не исходящее (чужое) — "
                             "отказ, ноль операций")
                if _thread_of(m) != topic:
                    sys.exit(f"tg-edit: id={mid} не в топике {topic} — "
                             "отказ, ноль операций")
                targets.append(m)
            if dry:
                for m in targets:
                    row = {"id": m.id, "topic": topic, "dry-run": True}
                    if delete_ids is not None:
                        row["delete"] = True
                    else:
                        new = str(edits[str(m.id)]).strip()
                        row["new_len"] = len(new)
                        row["new_preview"] = new[:120]
                    print(json.dumps(row, ensure_ascii=False))
                sys.stderr.write("tg-edit: dry-run, операций не выполнялось\n")
                return
            # Фаза 2: применить ВСЕ (edit_message либо delete_messages;
            # send нет в коде вообще).
            if delete_ids is not None:
                for m in targets:
                    await client.delete_messages(ent, m.id)
                    print(json.dumps({"id": m.id, "topic": topic,
                                      "deleted": True}, ensure_ascii=False))
                sys.stderr.write(f"tg-edit: topic={topic} "
                                 f"удалений={len(targets)}\n")
                return
            for m in targets:
                await client.edit_message(ent, m.id,
                                          str(edits[str(m.id)]).strip())
                print(json.dumps({"id": m.id, "topic": topic,
                                  "edited": True}, ensure_ascii=False))
            sys.stderr.write(f"tg-edit: topic={topic} правок={len(targets)}\n")

    asyncio.run(run())


def _thread_of(m):
    rt = getattr(m, "reply_to", None)
    if rt is None:
        return None
    return (getattr(rt, "reply_to_top_id", None)
            or getattr(rt, "reply_to_msg_id", None))


async def _topic_ids(client, entity):
    from telethon.tl.functions.messages import GetForumTopicsRequest
    r = await client(GetForumTopicsRequest(
        peer=entity, offset_date=None, offset_id=0, offset_topic=0, limit=100))
    return {t.id for t in r.topics}


async def _topic_exists(client, entity, topic):
    return topic in await _topic_ids(client, entity)


if __name__ == "__main__":
    main(sys.argv[1:])
