#!/usr/bin/env python3
"""tg-attach — fail-closed работа с вложениями ОДНОГО разрешённого топика.

Что делает:
  - --list:     metadata ВСЕХ вложений топика от ЛЮБОГО участника —
               не угадываем имена, просто показываем; байты НЕ качаются;
  - --download: скачать подходящие файлы (whitelist-префикс, только
               Ratibor) в контролируемый temp-каталог + SHA-256.
Никаких отправок, никакого чтения текстов сообщений в вывод (только
metadata), никакого group-wide read.

Жёсткие рамки (owner scope, инцидент 2026-10-14):
  - разрешённый topic: ровно 33 («Тэсты»); другие topics — отказ;
  - --list: все участники, без фильтра имён; sha256 — только если файл
    уже скачан ранее (лежит в ATTACH_DIR), само скачивание не запускаем;
  - --download: единственное условие авто-скачивания — filename prefix
    «Last Login» (регистронезависимо: 'Last Login' ловит 'Last login')
    + отправитель Ratibor (username RaKHamidov);
  - каталог: только /tmp/opencode/tg-topic-33-attachment/ (создаётся 0700);
  - секретоподобные файлы (.pem/.key/.env/id_rsa/*private* и т.п.) —
    НЕ качать, доложить только признак (secret-suspect-REFUSED).

Использование:
  python3 tg-attach.py --help
  python3 tg-attach.py --topic 33 --list [--limit N]
  python3 tg-attach.py --topic 33 --download [--limit N]
--list и --download взаимоисключаемы; без режима — отказ (fail-closed).

Зависимость: telethon (системно). Секреты — только ~/.config/ssa-tg/tg.env.
"""
import hashlib
import json
import os
import sys

ENV_FILE = os.path.expanduser("~/.config/ssa-tg/tg.env")
SESSION = os.path.expanduser("~/.local/state/ssa-tg/ssa.session")
STATE_DIR = os.path.expanduser("~/.local/state/ssa-tg")

ALLOWED_TOPICS = {33}
ALLOWED_SENDER = "rakhamidov"
FILENAME_PREFIX = "Last Login"
ATTACH_DIR = "/tmp/opencode/tg-topic-33-attachment"

SECRET_HINTS = (".pem", ".key", ".env", "id_rsa", "private", ".pfx", ".p12",
                "credentials", "secret")

USAGE = """tg-attach --topic 33 (--list | --download) [--limit N]
  --topic 33   разрешён ровно topic 33 (другие — отказ, чтения нет)
  --list       metadata ВСЕХ вложений топика от любого участника:
               filename, mime, size, sha256 (если файл уже скачан),
               message_id, from — без текстов сообщений, без скачивания
  --download   скачать подходящие (префикс «Last Login», регистронезависимо,
               отправитель Ratibor) + SHA-256; содержимое НЕ в вывод
  --limit N    сколько сообщений топика сканировать (default 50, max 200)
--list и --download вместе — отказ; без режима — отказ (fail-closed).
Вывод: только metadata JSON-строками {topic, message_id, from, filename,
mime, size, classification, sha256?, path?}. Тексты и байты — никогда."""


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


def looks_secret(name, mime):
    blob = f"{name} {mime}".lower()
    return any(h in blob for h in SECRET_HINTS)


def classify(mime, name):
    mime = (mime or "").lower()
    if mime.startswith("image/"):
        return "image"
    if mime == "application/pdf":
        return "document-pdf"
    if mime in ("application/zip", "application/x-rar",
                "application/x-7z-compressed", "application/gzip"):
        return "archive"
    if mime.startswith(("text/", "application/json")):
        return "text-data"
    if mime.startswith(("application/x-msdownload", "application/x-sh",
                         "application/x-executable")):
        return "executable-suspicious"
    return "document-other"


def _prefix_match(name, prefix):
    """Whitelist-префикс, регистронезависимо: 'Last Login' ловит 'Last login'."""
    return name.casefold().startswith(prefix.casefold())


def _local_path(message_id, name):
    """Путь уже скачанного файла в ATTACH_DIR ('' — если не скачан)."""
    if not name:
        return ""
    safe = "".join(c for c in name if c not in "/\\\0").strip() or "file"
    p = os.path.join(ATTACH_DIR, f"{message_id}_{safe}")
    return p if os.path.exists(p) else ""


def _metadata(topic, m, doc, name, sender):
    """Metadata одного вложения: без текстов сообщений, без байтов.
    sha256 — только если файл уже лежит скачанный в ATTACH_DIR."""
    meta = {"topic": topic,
            "message_id": m.id,
            "from": sender,
            "filename": name,
            "mime": doc.mime_type or "",
            "size": doc.size or 0,
            "classification": classify(doc.mime_type or "", name)}
    if looks_secret(name, doc.mime_type or ""):
        meta["classification"] = "secret-suspect"
    local = _local_path(m.id, name)
    if local:
        meta["path"] = local
        meta["sha256"] = _sha256(local)
    return meta


def main(argv):
    if "--help" in argv or "-h" in argv:
        print(USAGE)  # безвредно: до сети, env и диска не доходим
        return
    limit = 50
    topic = None
    known_vals = set()
    if "--limit" in argv:
        i = argv.index("--limit")
        limit = min(int(argv[i + 1]), 200)
        known_vals.add(argv[i + 1])
    if "--topic" in argv:
        i = argv.index("--topic")
        topic = int(argv[i + 1])
        known_vals.add(argv[i + 1])
    want_list = "--list" in argv
    want_download = "--download" in argv
    if want_list and want_download:
        sys.exit("tg-attach: --list и --download вместе — отказ (см. --help)")
    mode = "list" if want_list else ("download" if want_download else None)
    allowed = {"--limit", "--topic", "--list", "--download"} | known_vals
    stray = [a for a in argv if a not in allowed]
    if stray:
        sys.exit(f"tg-attach: неизвестные аргументы {stray} — отказ (см. --help)")
    if topic is None:
        sys.exit("tg-attach: нет --topic ID — отказ (fail-closed; см. --help)")
    if topic not in ALLOWED_TOPICS:
        sys.exit(f"tg-attach: topic {topic} вне разрешённого scope "
                 f"(разрешён: {sorted(ALLOWED_TOPICS)}) — отказ")
    if mode is None:
        sys.exit("tg-attach: нет режима (--list или --download) — отказ "
                 "(fail-closed; см. --help)")

    env = load_env(ENV_FILE)
    api_id = env.get("TG_API_ID", "")
    api_hash = env.get("TG_API_HASH", "")
    group = env.get("SSA_GROUP_ID", "")
    proxy = parse_proxy(env.get("TG_PROXY", ""))
    if not api_id or not api_hash or not group:
        sys.exit("tg-attach: заполни TG_API_ID/TG_API_HASH/SSA_GROUP_ID в " + ENV_FILE)
    try:
        from telethon import TelegramClient
    except ImportError:
        sys.exit("tg-attach: нет telethon")
    try:
        import python_socks  # noqa: F401
    except ImportError:
        if proxy is not None:
            sys.exit("tg-attach: задан TG_PROXY, но нет python-socks")

    import asyncio

    async def run():
        async with TelegramClient(SESSION, int(api_id), api_hash,
                                  proxy=proxy) as client:
            ent = await client.get_entity(int(group))
            topics = await _topic_ids(client, ent)
            if topic not in topics:
                sys.exit(f"tg-attach: топика {topic} нет в группе — отказ")
            # Только вложения топика: reply_to изолирует тему, текстовый
            # вывод скрипта не содержит body сообщений.
            msgs = await client.get_messages(ent, limit=limit,
                                             reply_to=topic)
            found = []
            for m in sorted(msgs, key=lambda x: x.id):
                doc = m.document
                if doc is None:
                    continue
                name = _filename(m) or ""
                sender = await _sender(m)
                if mode == "list":
                    # ВСЕ вложения, любой участник — имена не угадываем.
                    found.append(_metadata(topic, m, doc, name, sender))
                    continue
                # --download: whitelist-префикс (регистронезависимо) + Ratibor.
                if not name or not _prefix_match(name, FILENAME_PREFIX):
                    continue
                if sender.lower() != ALLOWED_SENDER:
                    continue
                meta = _metadata(topic, m, doc, name, sender)
                if meta["classification"] == "secret-suspect":
                    meta["classification"] = "secret-suspect-REFUSED"
                    found.append(meta)
                    continue
                meta["path"] = await _download(client, m, name)
                meta["sha256"] = _sha256(meta["path"])
                found.append(meta)
            for row in found:
                print(json.dumps(row, ensure_ascii=False))
            sys.stderr.write(f"tg-attach: topic={topic} mode={mode} "
                             f"вложений={len(found)}\n")

    asyncio.run(run())


async def _topic_ids(client, entity):
    from telethon.tl.functions.messages import GetForumTopicsRequest
    r = await client(GetForumTopicsRequest(
        peer=entity, offset_date=None, offset_id=0, offset_topic=0, limit=100))
    return {t.id for t in r.topics}


async def _sender(m):
    try:
        s = await m.get_sender()
        return getattr(s, "username", "") or ""
    except Exception:  # noqa: BLE001
        return "?"


def _filename(m):
    for attr in (m.document.attributes or []):
        if hasattr(attr, "file_name") and attr.file_name:
            return os.path.basename(attr.file_name)
    return ""


async def _download(client, m, name):
    os.makedirs(ATTACH_DIR, mode=0o700, exist_ok=True)
    safe = "".join(c for c in name if c not in "/\\\0").strip() or "file"
    dest = os.path.join(ATTACH_DIR, f"{m.id}_{safe}")
    return await client.download_media(m, file=dest)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    main(sys.argv[1:])
