#!/usr/bin/env python3
"""tg-watch — пуш-гейт топика 33: событийное (не поллинг) чтение в JSON-поток.

Что делает:
  - слушает НОВЫЕ сообщения форумного топика 33 («Тэсты») группы SSA через
    Telethon-события (events.NewMessage) — никаких get_messages-поллингов;
  - на каждое новое сообщение — ровно одна JSON-строка в stdout:
    {id, topic, from, date, type, filename, mime, size, sha256, text_preview};
  - stdout — только поток событий для consumer'а; статус/диагностика — stderr;
    в логи и файлы НИЧЕГО не пишется.

Безопасность (read-only, fail-closed):
  - физически никакой отправки/редактирования: send_message/edit_message/
    delete в коде нет даже импортом; только события + потоковое чтение медиа;
  - --topic ОБЯЗАТЕЛЕН и строго 33 (ALLOWED_TOPICS={33}); без топика, с
    другим топиком или неизвестным флагом — отказ ДО env/сети (rc=1);
  - текст поста — только text_preview, максимум 200 символов;
  - sha256 медиа — байты скачиваются ПОТОКОВО (iter_download) и хешируются
    на лету; файл на диск НЕ сохраняется; при type != file или сбое
    скачивания — null;
  - --help работает без сети/env и с rc=0;
  - секреты — только ~/.config/ssa-tg/tg.env, никогда из аргументов/репо.

Конкуренция за сессию — режим КОПИИ (не flock):
  Telethon-сессию держат короткие скрипты (tg-send/tg-read/мост). flock на
  sidecar-.lock защищал бы только watch от watch (остальные скрипты лок не
  берут — ложная гарантия), а долгий watch блокировал бы живую отправку.
  Поэтому: watch всегда работает на ОТДЕЛЬНОЙ КОПИИ сессии
  ~/.local/state/ssa-tg/ssa<suffix>.session (суффикс по умолчанию «-watch»,
  меняется --session-suffix). Копия создаётся один раз при старте из
  базовой ssa.session (содержит тот же auth-ключ — второй легитимный
  логин того же аккаунта, как второе устройство). Конфликта нет: мост и
  watch ходят разными файлами сессии.

Использование:
  python3 tg-watch.py --help
  python3 tg-watch.py --topic 33 [--limit-seconds N] [--session-suffix S]
  --limit-seconds N  автостоп через N секунд (0 — умолчание — вечно до SIGTERM)

Зависимость: telethon (системно, ставит владелец: pip install --user telethon).
Запуск: python3 scripts/.local/bin/tg-watch.py --topic 33
    (exec-бит ставит владелец: chmod +x — вне зоны агента).
"""
import asyncio
import hashlib
import json
import os
import shutil
import signal
import sys
import time

ENV_FILE = os.path.expanduser("~/.config/ssa-tg/tg.env")
SESSION = os.path.expanduser("~/.local/state/ssa-tg/ssa.session")
STATE_DIR = os.path.expanduser("~/.local/state/ssa-tg")

# Живое чтение — только этот topic (симметрия tg-send/tg-attach).
ALLOWED_TOPICS = {33}
DEFAULT_SUFFIX = "-watch"
PREVIEW_LIMIT = 200

USAGE = """tg-watch --topic 33 [--limit-seconds N] [--session-suffix S]
  --topic ID        ID форумного топика (обязателен; строго 33, иное — отказ
                    ДО env/сети; group-wide watch отключён)
  --limit-seconds N автостоп через N секунд (default 0 = вечно до SIGTERM/SIGINT)
  --session-suffix S  имя копии сессии: ssa<S>.session (default «-watch» ->
                    ssa-watch.session). Конкуренция за сессию решена КОПИЕЙ
                    (не flock): лок защищал бы только watch-от-watch'а, а
                    долгий watch блокировал бы отправку остальных скриптов;
                    копия — независимый второй логин того же аккаунта,
                    создаётся один раз из базовой ssa.session при старте.
Read-only: событийная модель (NewMessage), поллинга нет; физической отправки/
редактирования в коде нет (send/edit не импортируются). Вывод: по одной
JSON-строке на новое сообщение в stdout:
  {id, topic, from, date, type: text|file|other, filename, mime, size,
   sha256, text_preview}
text_preview — только текст поста, максимум 200 символов. sha256 — потоковый
хеш медиа (iter_download, байты в память, на диск НЕ пишем); при type != file
или сбое скачивания — null. В логи/файлы ничего не пишется, stdout — только
для consumer'а; статус — в stderr."""


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


def _int_or_exit(name, raw):
    """Число из argv с чистым отказом (fail-closed, без traceback)."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        sys.exit(f"tg-watch: {name} ожидает целое число, получено {raw!r} — "
                 f"отказ (см. --help)")


def _valid_suffix(suffix):
    """Суффикс копии сессии — только безопасное имя внутри STATE_DIR."""
    return (suffix
            and "/" not in suffix and "\\" not in suffix
            and ".." not in suffix and not suffix.startswith("."))


def prepare_session(suffix):
    """Копия сессии для изоляции конкуренции. -> путь к сессии watch."""
    if not _valid_suffix(suffix):
        sys.exit(f"tg-watch: небезопасный --session-suffix {suffix!r} — "
                 f"отказ (только имя файла без путей, см. --help)")
    session = os.path.join(STATE_DIR, f"ssa{suffix}.session")
    if not os.path.exists(session):
        if not os.path.exists(SESSION):
            sys.exit("tg-watch: нет базовой сессии " + SESSION +
                     " — сначала залогинься (tg-login.py) — отказ")
        os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
        shutil.copyfile(SESSION, session)
        sys.stderr.write(f"tg-watch: копия сессии создана из базовой -> "
                         f"{session} (независимый логин, конкуренции нет)\n")
    return session


def _thread_of(m):
    """ID топика сообщения (как в canon tg-edit): reply_to_top_id или msg_id."""
    rt = getattr(m, "reply_to", None)
    if rt is None:
        return None
    return (getattr(rt, "reply_to_top_id", None)
            or getattr(rt, "reply_to_msg_id", None))


def _kind_of(m):
    """Классификация: file (медиа с байтами) | text (текст без медиа) | other."""
    if getattr(m, "photo", None) is not None or getattr(m, "document", None) is not None:
        return "file"
    if m.text:
        return "text"
    return "other"


def _media_meta(m):
    """(filename, mime, size) медиа — только metadata, байт на диск не кладём."""
    doc = getattr(m, "document", None)
    if doc is not None:
        name = ""
        for attr in (doc.attributes or []):
            if hasattr(attr, "file_name") and attr.file_name:
                name = os.path.basename(attr.file_name)
                break
        return name, (doc.mime_type or ""), (doc.size or 0)
    if getattr(m, "photo", None) is not None:
        # Фото: имя не угадываем; mime — канон TG для фото; размер — из
        # File-обёртки, если Telethon его отдаёт.
        try:
            size = m.file.size or 0
        except Exception:  # noqa: BLE001
            size = 0
        return "", "image/jpeg", size
    return "", "", 0


async def _sender_name(m):
    """Имя отправителя (как tg-read): username | имя | id, сбой -> '?'."""
    try:
        s = await m.get_sender()
        return (getattr(s, "username", "") or
                f"{getattr(s, 'first_name', '')} "
                f"{getattr(s, 'last_name', '')}".strip() or
                str(getattr(s, "id", "")))
    except Exception:  # noqa: BLE001
        return "?"


async def _sha256_media(client, m):
    """Потоковый хеш медиа: chunk -> hashlib, на диск НЕ пишем. Сбой -> None."""
    h = hashlib.sha256()
    try:
        async for chunk in client.iter_download(m):
            h.update(chunk)
    except Exception as e:  # noqa: BLE001 — sha256 null, сообщение не теряем
        sys.stderr.write(f"tg-watch: sha256: потоковое скачивание не удалось "
                         f"(id={m.id}, {e!r}) — null\n")
        return None
    return h.hexdigest()


async def _row(client, m, topic):
    """Одна JSON-запись события (поля — по спеке гейта)."""
    kind = _kind_of(m)
    filename, mime, size = _media_meta(m) if kind == "file" else ("", "", 0)
    return {
        "id": m.id,
        "topic": topic,
        "from": await _sender_name(m),
        "date": m.date.isoformat() if m.date else "",
        "type": kind,
        "filename": filename,
        "mime": mime,
        "size": size,
        "sha256": await _sha256_media(client, m) if kind == "file" else None,
        "text_preview": (m.text or "")[:PREVIEW_LIMIT],
    }


def main(argv):
    if "--help" in argv or "-h" in argv:
        print(USAGE)  # безвредно: до env, сети и сессии не доходим
        return 0
    topic = None
    limit_seconds = 0
    suffix = DEFAULT_SUFFIX
    known_vals = set()
    if "--topic" in argv:
        i = argv.index("--topic")
        if i + 1 >= len(argv):
            sys.exit("tg-watch: --topic без значения — отказ (см. --help)")
        topic = _int_or_exit("--topic", argv[i + 1])
        known_vals.add(argv[i + 1])
    if "--limit-seconds" in argv:
        i = argv.index("--limit-seconds")
        if i + 1 >= len(argv):
            sys.exit("tg-watch: --limit-seconds без значения — отказ "
                     "(см. --help)")
        limit_seconds = _int_or_exit("--limit-seconds", argv[i + 1])
        known_vals.add(argv[i + 1])
    if "--session-suffix" in argv:
        i = argv.index("--session-suffix")
        if i + 1 >= len(argv):
            sys.exit("tg-watch: --session-suffix без значения — отказ "
                     "(см. --help)")
        suffix = argv[i + 1]
        known_vals.add(argv[i + 1])
    # строже: любой токен вне известных флагов/значений — отказ
    allowed = {"--topic", "--limit-seconds", "--session-suffix"} | known_vals
    stray = [a for a in argv if a not in allowed]
    if stray:
        sys.exit(f"tg-watch: неизвестные аргументы {stray} — отказ (см. --help)")
    if topic is None:
        sys.exit("tg-watch: нет --topic ID — живое слушание запрещено "
                 "(fail-closed, group-wide watch отключён; см. --help)")
    if topic not in ALLOWED_TOPICS:
        sys.exit(f"tg-watch: topic {topic} вне разрешённого scope "
                 f"(разрешён: {sorted(ALLOWED_TOPICS)}) — отказ ДО env/сети "
                 f"(см. --help)")
    if limit_seconds < 0:
        sys.exit("tg-watch: --limit-seconds не может быть отрицательным — "
                 "отказ (см. --help)")

    env = load_env(ENV_FILE)
    api_id = env.get("TG_API_ID", "")
    api_hash = env.get("TG_API_HASH", "")
    group = env.get("SSA_GROUP_ID", "")
    proxy = parse_proxy(env.get("TG_PROXY", ""))
    if not api_id or not api_hash or not group:
        sys.exit("tg-watch: заполни TG_API_ID/TG_API_HASH/SSA_GROUP_ID в " + ENV_FILE)
    try:
        from telethon import TelegramClient, events
    except ImportError:
        sys.exit("tg-watch: нет telethon (владелец ставит: "
                 "pip install --user telethon)")
    try:
        import python_socks  # noqa: F401  (нужен telethon для TG_PROXY)
    except ImportError:
        if proxy is not None:
            sys.exit("tg-watch: задан TG_PROXY, но нет python-socks "
                     "(владелец ставит: pip install --user "
                     "'python-socks[asyncio]')")

    session = prepare_session(suffix)

    async def run():
        seen = 0
        stop = asyncio.Event()

        async with TelegramClient(session, int(api_id), api_hash,
                                  proxy=proxy) as client:
            me = await client.get_me()
            ent = await client.get_entity(int(group))
            topics = await _topic_ids(client, ent)
            if topic not in topics:
                sys.exit(f"tg-watch: топика {topic} нет в группе "
                         f"(есть: {sorted(topics)}) — отказ")

            async def on_new_message(event):
                nonlocal seen
                m = event.message
                # Фильтр топика в обработчике (как _thread_of в canon):
                # событие приходит на всю группу, наружу — только topic 33.
                if _thread_of(m) != topic:
                    return
                row = await _row(client, m, topic)
                print(json.dumps(row, ensure_ascii=False), flush=True)
                seen += 1

            client.add_event_handler(
                on_new_message,
                events.NewMessage(chats=ent, incoming=True, outgoing=True))
            sys.stderr.write(f"tg-watch: как {me.username or me.id} -> "
                             f"{group} topic={topic} слушается "
                             f"(сессия-копия {os.path.basename(session)}, "
                             f"лимит {limit_seconds or '∞'}с)\n")

            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.add_signal_handler(sig, stop.set)
                except NotImplementedError:
                    pass  # не-posix: дефолтное поведение сигнала

            await _wait_or_stop(stop, limit_seconds)
            await client.disconnect()
        reason = (f"limit {limit_seconds}с" if limit_seconds else "сигнал")
        sys.stderr.write(f"tg-watch: остановка ({reason}), сообщений={seen}\n")
        return 0

    return asyncio.run(run())


async def _wait_or_stop(stop, limit_seconds):
    """Ждём stop-событие; limit_seconds>0 — автостоп по дедлайну (0 = вечно)."""
    if limit_seconds <= 0:
        await stop.wait()
        return
    deadline = time.monotonic() + limit_seconds
    while time.monotonic() < deadline:
        chunk = min(1.0, max(0.05, deadline - time.monotonic()))
        try:
            await asyncio.wait_for(stop.wait(), timeout=chunk)
            return  # стоп по сигналу раньше дедлайна
        except asyncio.TimeoutError:
            continue


async def _topic_ids(client, entity):
    """ID существующих топиков (только метаданные заголовков, без текстов)."""
    from telethon.tl.functions.messages import GetForumTopicsRequest
    r = await client(GetForumTopicsRequest(
        peer=entity, offset_date=None, offset_id=0, offset_topic=0, limit=100))
    return {t.id for t in r.topics}


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
