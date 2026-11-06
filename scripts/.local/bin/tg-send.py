#!/usr/bin/env python3
"""tg-send — отправка сообщения в рабочую группу от имени владельца
(профиль SSA по умолчанию; TG_PROFILE=dv — кабинет dv-hub, топик 1399).

Безопасность:
  - получатель ТОЛЬКО <GROUP_KEY> профиля из env (whitelist, переопределения нет);
  - живая отправка — только ALLOWED_TOPICS профиля (ssa: 33, dv: 1399);
    другой topic — отказ ДО env/сети; --dry-run — любой topic, полностью без сети;
  - секреты только из env-файла профиля, никогда из аргументов/репо;
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tg_profile  # noqa: E402

_PROFILE = tg_profile.profile()
ENV_FILE, SESSION, _STATE_DIR = tg_profile.paths()

# Живая отправка — только эти topics профиля (симметрия tg-attach/tg-upload);
# --dry-run не ограничен и не ходит в сеть.
ALLOWED_TOPICS = set(_PROFILE.get("allowed_topics") or [])

USAGE = """tg-send --topic ID [--reply-to ID] [--format md|plain] [--dry-run] [--file TEXTFILE] [ТЕКСТ ...]
  --topic ID   ID форумного топика (обязателен; без него отправки нет)
  --reply-to ID  ID сообщения для прямого ответа внутри этого топика
  --format F   разметка: md (умолчание) | plain (как есть, без разбора)
  --dry-run    показать исходный текст + план entities (до сети), не отправлять
  --file PATH  взять текст из файла (иначе — аргументы или stdin)
Живая отправка: только разрешённые topics (сейчас 33) — другой topic
даёт отказ ДО env/сети; --dry-run безвреден для любого topic (без сети).
Получатель всегда один — группа SSA из env (whitelist, не меняется).
md-разметка: **жирный**, `код`, ```блок``` (Telethon Markdown).
Падение md-парсинга -> plain без маркеров + warning в stderr (не теряем)."""


def load_env(path):
    """Оставлено для совместимости (см. tg_profile.load_env)."""
    return tg_profile.load_env(path)


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


def _print_dry_run(group, topic, reply_to, fmt, text, wire, entities):
    print(f"dry-run -> chat {group} topic={topic} reply_to={reply_to} "
          f"format={fmt} (до сети; без отправки)")
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
    reply_to = None
    known_vals = set()
    if "--topic" in argv:
        i = argv.index("--topic")
        topic = int(argv[i + 1])
        known_vals.add(argv[i + 1])
    if "--reply-to" in argv:
        i = argv.index("--reply-to")
        reply_to = int(argv[i + 1])
        known_vals.add(argv[i + 1])
    # reply_to=0 в живой отправке гасит forum_topic: сообщение уезжает в
    # общий поток вместо топика (инцидент маршрутизации 2026-11-05).
    # 0 = «без ответа», а не «ответ на сообщение №0».
    if reply_to is not None and reply_to <= 0:
        sys.stderr.write("tg-send: reply_to<=0 трактуется как «без ответа» "
                         "(иначе сообщение уходит в общий поток)\n")
        reply_to = None
    rest = [a for a in argv if a not in ("--topic", "--reply-to")]
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
    if topic is None and not _PROFILE.get("chat_scope"):
        sys.exit("tg-send: нет --topic ID — отправка запрещена "
                 "(fail-closed; см. --help)")
    if not dry and not _PROFILE.get("chat_scope") and topic not in ALLOWED_TOPICS:
        sys.exit(f"tg-send: topic {topic} вне разрешённого scope для живой "
                 f"отправки (разрешён: {sorted(ALLOWED_TOPICS)}) — отказ "
                 f"ДО env/сети; --dry-run безвреден для любого topic "
                 f"(см. --help)")

    env = tg_profile.load_env(ENV_FILE) if os.path.exists(ENV_FILE) else {}
    api_id = env.get("TG_API_ID", "")
    api_hash = env.get("TG_API_HASH", "")
    group = env.get(_PROFILE["group_key"], "") or _PROFILE.get("group_default", "")
    proxy = tg_profile.parse_proxy(env.get("TG_PROXY", ""))
    if not api_id or not api_hash or not group:
        if not dry:
            sys.exit(f"tg-send: заполни TG_API_ID/TG_API_HASH/{_PROFILE['group_key']} "
                     f"в {ENV_FILE}")
        # dry-run: env может быть не создан (профиль dv до шага владельца) —
        # placeholder группы из профиля, секретов нет, сеть не нужна
        tg_profile.journal_append({"action": "dry-run-noenv", "topic": topic,
                                   "reason": "env-missing-placeholder"})
    if not os.path.exists(SESSION) or os.path.getsize(SESSION) == 0:
        sys.exit("tg-bridge: нет действующей сессии " + SESSION + " — "
                 "сначала вход: tg-login.py (профиль " + _PROFILE["name"]
                 + "); пустой файл сессии убери, если появился")
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
        _print_dry_run(group, topic if topic else "chat", reply_to, fmt, text,
                       wire, entities)
        tg_profile.journal_append({"action": "dry-run", "topic": topic, "fmt": fmt,
                                   "entities": len(entities) if entities else 0,
                                   "text_preview": tg_profile.preview(text)})
        return  # до сети: Telethon-клиент не запускаем

    async def send():
        async with TelegramClient(SESSION, int(api_id), api_hash,
                                  proxy=proxy) as client:
            me = await client.get_me()
            ent = await client.get_entity(int(group))
            chat_scope = bool(_PROFILE.get("chat_scope"))
            if topic is not None:
                topics = await _topic_ids(client, ent)
                if topic not in topics:
                    sys.exit(f"tg-send: топика {topic} нет в группе "
                             f"(есть: {sorted(topics)}) — отказ")
            scope_txt = f"topic={topic}" if topic is not None else "chat"
            if reply_to is not None:
                scope_txt += f" reply_to={reply_to}"
            sys.stderr.write(f"tg-send: как {me.username or me.id} -> {group} "
                             f"{scope_txt} format={fmt}\n")
            # Повтор: Telethon иногда падает на разборе TL (отставание схемы к
            # слою сервера) — одно и то же сообщение уходит со второй попытки.
            # Без повтора теряется отправка, которую должен увидеть человек.
            last_err: Exception | None = None
            msg = None
            for attempt in (1, 2, 3):
                try:
                    msg = await client.send_message(
                        ent, wire,
                        **({"reply_to": reply_to if reply_to is not None
                            else topic} if (reply_to is not None
                                            or topic is not None) else {}),
                        parse_mode=None, formatting_entities=entities)
                    break
                except Exception as e:  # noqa: BLE001 — только повтор
                    last_err = e
                    sys.stderr.write(f"tg-send: попытка {attempt} не удалась "
                                     f"({type(e).__name__}); повтор\n")
                    await asyncio.sleep(1.5)
            if msg is None:
                raise last_err if last_err else RuntimeError("send failed")
            print(f"tg-send: ok id={msg.id} {scope_txt}")
            tg_profile.journal_append({"action": "sent", "topic": topic,
                                       "reply_to": reply_to,
                                       "msg_id": msg.id, "fmt": fmt,
                                       "text_preview": tg_profile.preview(text)})

    asyncio.run(send())


async def _topic_ids(client, entity):
    """ID существующих топиков (только метаданные заголовков, без текстов)."""
    from telethon.tl.functions.messages import GetForumTopicsRequest
    r = await client(GetForumTopicsRequest(
        peer=entity, offset_date=None, offset_id=0, offset_topic=0, limit=100))
    return {t.id for t in r.topics}


if __name__ == "__main__":
    main(sys.argv[1:])
