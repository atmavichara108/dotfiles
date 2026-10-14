#!/usr/bin/env python3
"""tg-send — отправка сообщения в рабочую группу SSA от имени владельца.

Безопасность:
  - получатель ТОЛЬКО SSA_GROUP_ID из env (whitelist, переопределения нет);
  - секреты только из ~/.config/ssa-tg/tg.env, никогда из аргументов/репо;
  - запуск: python3 tg-send.py --topic ID [--format md|plain] [--dry-run]
        [--file TEXTFILE] [ТЕКСТ ...]
    (exec-бит ставит владелец: chmod +x — вне зоны агента).

Разметка (стандарт владельца; формат md — умолчание):
  - **жирный** — заголовки и акценты;
  - `код` — команды и пути (всегда в коде);
  - ```блоки``` — листинги (моноширинно; язык после ``` telethon-парсер
    не разбирает — уходит в текст блока);
  - --format plain — текст уходит как есть, без разбора разметки;
  - безопасный фолбэк: если md-парсинг падает — сообщение уходит plain
    БЕЗ маркеров + warning в stderr (сообщение не теряется);
  - --dry-run показывает исходный текст и план entities полностью ДО сети:
    Telethon-клиент не запускается, ничего не отправляется.

Зависимость: telethon (системно, ставит владелец: pip install --user telethon).
"""
import os
import re
import sys
import asyncio

ENV_FILE = os.path.expanduser("~/.config/ssa-tg/tg.env")
SESSION = os.path.expanduser("~/.local/state/ssa-tg/ssa.session")

USAGE = """tg-send --topic ID [--format md|plain] [--dry-run] [--file TEXTFILE] [ТЕКСТ ...]
  --topic ID   ID форумного топика (обязателен; без него отправки нет)
  --format F   разметка: md (умолчание) | plain (как есть, без разбора)
  --dry-run    показать исходный текст + план entities (до сети), не отправлять
  --file PATH  взять текст из файла (иначе — аргументы или stdin)
Получатель всегда один — группа SSA из env (whitelist, не меняется).
md-разметка: **жирный**, `код`, ```блок``` (Telethon Markdown).
Падение md-парсинга -> plain без маркеров + warning в stderr (не теряем)."""


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


def strip_md(text):
    """Best-effort: снять маркеры md для plain-фолбэка (текст не теряем).

    Сначала убираем fence-строки целиком (``` + опц. язык, только когда
    строка состоит из маркера), потом — оставшиеся парные маркеры.
    """
    t = re.sub(r"^[ \t]*(```+)[\w+-]*[ \t]*$", "", text, flags=re.M)
    return t.replace("**", "").replace("`", "")


def build_message(text, fmt):
    """Разбор разметки ДО сети. -> (wire_text, entities, warning).

    entities=None => уйдёт как plain. warning непустой => сработал
    безопасный фолбэк: сообщение не теряется в любом случае.
    """
    if fmt != "md":
        return text, None, ""
    try:
        from telethon.extensions import markdown
        wire, entities = markdown.parse(text)
        return wire, list(entities), ""
    except Exception as e:  # noqa: BLE001 — фолбэк обязателен: не теряем сообщение
        return (strip_md(text), None,
                f"tg-send: WARNING: md-парсинг упал ({e!r}) — "
                f"фолбэк: plain без маркеров")


def _u16_slice(text, offset, length):
    """Срез по UTF-16 оффсетам (MTProto считает оффсеты в utf-16 units)."""
    try:
        raw = text.encode("utf-16-le")
        return raw[offset * 2:(offset + length) * 2].decode("utf-16-le",
                                                            "replace")
    except Exception:  # noqa: BLE001
        return ""


def _print_dry_run(group, topic, fmt, text, wire, entities):
    print(f"dry-run -> chat {group} topic={topic} format={fmt} "
          f"(до сети; без отправки)")
    print("--- SOURCE TEXT ---")
    print(text)
    print("--- WIRE TEXT (что уйдёт в TG) ---")
    print(wire)
    n = len(entities) if entities else 0
    print(f"--- ENTITIES PLAN ({n}) ---")
    for e in entities or []:
        kind = type(e).__name__
        lang = getattr(e, "language", "")
        snippet = _u16_slice(wire, e.offset, e.length)[:60]
        extra = f" language={lang!r}" if lang else ""
        print(f"  {kind} offset={e.offset} length={e.length}{extra} «{snippet}»")
    if not n:
        print("  (нет — уйдёт как plain)")


def main(argv):
    if "--help" in argv or "-h" in argv:
        print(USAGE)  # безвредно: до сети и текста не доходим
        return
    dry = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]
    fmt = "md"
    if "--format" in argv:
        i = argv.index("--format")
        if i + 1 >= len(argv):
            sys.exit("tg-send: --format без значения (md|plain) — отказ "
                     "(см. --help)")
        fmt = argv[i + 1]
        if fmt not in ("md", "plain"):
            sys.exit(f"tg-send: неизвестный --format {fmt!r} (только md|plain) "
                     f"— отказ (см. --help)")
        argv = argv[:i] + argv[i + 2:]
    text = ""
    topic = None
    known_vals = set()
    if "--topic" in argv:
        i = argv.index("--topic")
        topic = int(argv[i + 1])
        known_vals.add(argv[i + 1])
    rest = [a for a in argv if a != "--topic"]
    if "--file" in rest:
        i = rest.index("--file")
        with open(rest[i + 1], encoding="utf-8") as f:
            text = f.read()
        known_vals.update([rest[i + 1]])
    else:
        words = [a for a in rest if a not in known_vals]
        stray = [a for a in words if a.startswith("--")]
        if stray:
            # флагоподобный текст никогда не отправляем (ловушка --help)
            sys.exit(f"tg-send: неизвестные флаги {stray} — отказ (см. --help)")
        text = " ".join(words) if words else sys.stdin.read()
    text = text.strip()
    if not text:
        sys.exit("tg-send: пустой текст — нечего отправлять")
    if topic is None:
        sys.exit("tg-send: нет --topic ID — отправка запрещена "
                 "(fail-closed; см. --help)")

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

    # Разбор разметки ДО сети: dry-run и фолбэк полностью офлайн.
    wire, entities, warning = build_message(text, fmt)
    if warning:
        sys.stderr.write(warning + "\n")
    if dry:
        _print_dry_run(group, topic, fmt, text, wire, entities)
        return  # до сети: Telethon-клиент не запускаем

    async def send():
        async with TelegramClient(SESSION, int(api_id), api_hash,
                                  proxy=proxy) as client:
            me = await client.get_me()
            ent = await client.get_entity(int(group))
            topics = await _topic_ids(client, ent)
            if topic not in topics:
                sys.exit(f"tg-send: топика {topic} нет в группе "
                         f"(есть: {sorted(topics)}) — отказ")
            sys.stderr.write(f"tg-send: как {me.username or me.id} -> {group} "
                             f"topic={topic} format={fmt}\n")
            msg = await client.send_message(ent, wire, reply_to=topic,
                                            parse_mode=None,
                                            formatting_entities=entities)
            print(f"tg-send: ok id={msg.id} topic={topic}")

    asyncio.run(send())


async def _topic_ids(client, entity):
    """ID существующих топиков (только метаданные заголовков, без текстов)."""
    from telethon.tl.functions.messages import GetForumTopicsRequest
    r = await client(GetForumTopicsRequest(
        peer=entity, offset_date=None, offset_id=0, offset_topic=0, limit=100))
    return {t.id for t in r.topics}


if __name__ == "__main__":
    main(sys.argv[1:])
