#!/usr/bin/env python3
"""tg-attach — fail-closed работа с вложениями ОДНОГО разрешённого топика.

Что делает: список метаданных вложений топика + скачивание ОДНОГО файла
в контролируемый temp-каталог. Никаких отправок, никакого чтения текстов
сообщений в вывод (только metadata), никакого group-wide read.

Жёсткие рамки текущей задачи (owner scope, инцидент 2026-10-14):
  - разрешённый topic: ровно 33 («Тэсты»); другие topics — отказ;
  - отправитель файла: только Ratibor (username RaKhamidov);
  - filename prefix: только «Last Login»;
  - каталог: только /tmp/opencode/tg-topic-33-attachment/ (создаётся 0700);
  - секретоподобные файлы (.pem/.key/.env/id_rsa/*private* и т.п.) — НЕ качать,
    доложить только признак.

Использование:
  python3 tg-attach.py --help
  python3 tg-attach.py --topic 33 [--limit N] [--download]
Без --download — только metadata-список вложений топика (без текстов сообщений).
С --download — скачать подходящий файл + SHA-256 (содержимое НИКОГДА не в вывод).

Зависимость: telethon (системно). Секреты — только ~/.config/ssa-tg/tg.env.
"""
import fnmatch
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

USAGE = """tg-attach --topic 33 [--limit N] [--download]
  --topic 33   разрешён ровно topic 33 (другие — отказ, чтения нет)
  --limit N    сколько сообщений топика сканировать (default 50, max 200)
  --download   скачать подходящий файл (Ratibor, prefix «Last Login»)
Вывод: только metadata {topic, message_id, from, filename, mime, size,
sha256, classification, path}. Тексты сообщений и байты файлов — никогда."""


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


def main(argv):
    if "--help" in argv or "-h" in argv:
        print(USAGE)  # безвредно: до сети, env и диска не доходим
        return
    limit = 50
    download = False
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
    if "--download" in argv:
        download = True
    allowed = {"--limit", "--topic", "--download"} | known_vals
    stray = [a for a in argv if a not in allowed]
    if stray:
        sys.exit(f"tg-attach: неизвестные аргументы {stray} — отказ (см. --help)")
    if topic is None:
        sys.exit("tg-attach: нет --topic ID — отказ (fail-closed; см. --help)")
    if topic not in ALLOWED_TOPICS:
        sys.exit(f"tg-attach: topic {topic} вне разрешённого scope "
                 f"(разрешён: {sorted(ALLOWED_TOPICS)}) — отказ")

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
                if not name or not fnmatch.fnmatch(name, FILENAME_PREFIX + "*"):
                    continue
                if sender.lower() != ALLOWED_SENDER:
                    continue
                meta = {"topic": topic,
                        "message_id": m.id,
                        "from": sender,
                        "filename": name,
                        "mime": doc.mime_type or "",
                        "size": doc.size or 0,
                        "classification": classify(doc.mime_type or "", name),
                        "path": ""}
                if looks_secret(name, doc.mime_type or ""):
                    meta["classification"] = "secret-suspect-REFUSED"
                    found.append(meta)
                    continue
                if download:
                    meta["path"] = await _download(client, m, name)
                    meta["sha256"] = _sha256(meta["path"])
                found.append(meta)
            for row in found:
                print(json.dumps(row, ensure_ascii=False))
            sys.stderr.write(f"tg-attach: topic={topic} вложений "
                             f"по фильтру={len(found)}\n")

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
