#!/usr/bin/env python3
"""tg-guard — постоянный push-сторож TG-топика 33 (долгоживущий демон, user-юнит).

Дизайн (апрув владельца 2026-10-18; конвенция — control/docs/tg-comms-rules.md,
раздел «Постоянный канал tg-guard»):
  - ядро = tg-watch.py (push-слушатель, Telethon events.NewMessage, без
    поллинга, read-only) — импортируется как модуль, не копируется;
  - каждое сообщение топика 33 (входящие + исходящие, для аудита) — одна
    JSON-строка в append-only журнал
    ~/.local/state/ssa-tg/guard-journal.jsonl: метаданные + text_preview
    <= 200 символов; без полного тела, без секретов;
  - на входящее (from != username владельца) — wake координатора: POST
    /api/session/<id>/prompt в локальный OpenCode-сервер (opencode-serve,
    127.0.0.1:49374 по умолчанию). Basic-auth токен читается из
    ~/.config/opencode/service.json и НИКОГДА не логируется/не выводится;
    сессия координатора резолвится по названию «Control top» (не по модели,
    не по хардкод-ид: сессии могут пересоздаваться).

Wake — fail-open (апрув владельца 2026-10-18):
  - журнал пишется ВСЕГДА и первым; wake — best-effort;
  - сервер/сессия недоступны — событие НЕ теряется (осталось в журнале):
    строка журнала помечается wake="failed" + wake_err (без секретов),
    демон продолжает слушать без блокировки приёма;
  - реакция на не разбуженные события — при следующей сессии: координатор
    читает tail журнала при старте.

Безопасность (read-only, fail-closed по аргументам):
  - отправки/редактирования/удаления в коде нет: ядро tg-watch не имеет
    send_message/edit_message/delete — ничего не добавляется;
  - --topic строго 33 (ALLOWED_TOPICS={33}), неизвестный аргумент — отказ
    ДО env/сети (rc=1);
  - секреты (TG_API_ID/TG_API_HASH, service-токен) — только в
    ~/.config/ssa-tg/tg.env и ~/.config/opencode/service.json; никогда в
    argv, журнале, логах;
  - собственная копия сессии ssa-guard.session (второй легитимный логин
    того же аккаунта) — как в tg-watch;
  - wake-ошибка: один повтор с перерезолвом сессии; без слепых ретрай-циклов
    (следующее входящее попробует снова).

Запуск: user-юнит tg-guard.service (Restart=always); активация — владельцем:
  systemctl --user daemon-reload && systemctl --user enable --now tg-guard
Вручную: python3 tg-guard.py --topic 33
Остановка: SIGTERM/SIGINT — чистый exit.
"""
from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# --- ядро: tg-watch.py (импорт как модуль, без копирования кода) ----------
_HERE = os.path.dirname(os.path.abspath(__file__))
_SPEC = importlib.util.spec_from_file_location(
    "tg_watch_core", os.path.join(_HERE, "tg-watch.py"))
if _SPEC is None or _SPEC.loader is None:
    sys.exit("tg-guard: не удалось загрузить ядро tg-watch.py — отказ")
watch = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(watch)  # безопасно: main под __main__-гардом

JOURNAL_DIR = os.path.expanduser("~/.local/state/ssa-tg")
JOURNAL = os.path.join(JOURNAL_DIR, "guard-journal.jsonl")
GUARD_SESSION_SUFFIX = "-guard"
OUR_USER = "Atma_Vichara108"  # username владельца = отправитель tg-send
COORD_TITLE = "Control top"   # название сессии координатора (handshake)
SERVICE_JSON = os.path.expanduser("~/.config/opencode/service.json")
OPENCODE_ENDPOINT = os.environ.get("OPENCODE_ENDPOINT",
                                   "http://127.0.0.1:49374")
OPENCODE_SERVICE_USER = os.environ.get("OPENCODE_SERVICE_USER", "opencode")
WAKE_TIMEOUT = 10.0
PREVIEW = 200
ALLOWED_TOPICS = watch.ALLOWED_TOPICS  # {33} — строже, из ядра

USAGE = """tg-guard --topic 33
Постоянный push-сторож топика 33 (user-юнит tg-guard.service, Restart=always).
  --topic ID        ID форумного топика (обязателен; строго 33, иное — отказ
                    ДО env/сети)
Журнал (append-only, единственный источник правды по событиям):
  ~/.local/state/ssa-tg/guard-journal.jsonl
  строка: {ts, id, topic, from, date, type, filename, mime, size, sha256,
           text_preview(<=200), wake: ok|failed|skipped[, wake_err]}
Wake (fail-open): на входящее (from != %s) — POST /api/session/<id>/prompt
в локальный OpenCode-сервер (%s по умолчанию, переопределение env
OPENCODE_ENDPOINT); сессия координатора — по названию «%s»; токен — из
~/.config/opencode/service.json (нигде не логируется). Сервер/сессия
недоступны — событие остаётся в журнале с wake="failed", демон продолжает
слушать; реакция по журналу при следующей сессии.
Read-only: send/edit/delete в коде нет. Секреты — только в env/service.json.
Запуск: python3 tg-guard.py --topic 33 (или через юнит).
""" % (OUR_USER, OPENCODE_ENDPOINT, COORD_TITLE)


def journal_append(entry: dict) -> None:
    """Одна JSON-строка в append-only журнал (dir 0700, file 0600, fsync)."""
    os.makedirs(JOURNAL_DIR, mode=0o700, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False)
    fd = os.open(JOURNAL, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def _service_token():
    """Basic-auth токен из service.json (поле password); None — нет/сбой."""
    try:
        with open(SERVICE_JSON, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001
        return None
    tok = data.get("password") if isinstance(data, dict) else None
    return tok if isinstance(tok, str) and tok else None


def _basic_auth(tok: str) -> str:
    return "Basic " + base64.b64encode(
        f"{OPENCODE_SERVICE_USER}:{tok}".encode()).decode()


_coord_session_id: str | None = None


MAX_SESSION_PAGES = 20


def _page_sessions(tok: str, url: str):
    """GET страницы сессий -> (rows, next_cursor); сбой -> (None, None).

    Формат сервера v2 — envelope {data: [...], cursor: {previous, next}}
    с пейджингом (~50/страница); голый список (старые версии) — совместимо.
    """
    req = urllib.request.Request(url,
                                 headers={"Authorization": _basic_auth(tok)})
    with urllib.request.urlopen(req, timeout=WAKE_TIMEOUT) as r:
        body = json.loads(r.read().decode())
    if isinstance(body, list):
        return body, None
    if isinstance(body, dict) and isinstance(body.get("data"), list):
        cur = body.get("cursor")
        nxt = cur.get("next") if isinstance(cur, dict) else None
        return body["data"], (nxt if isinstance(nxt, str) and nxt else None)
    return None, None


def _resolve_coord_session(tok: str) -> str | None:
    """GET /api/session (envelope + ограниченное пейджингом) -> сессия
    по title == «Control top».

    Кэшируется в _coord_session_id; при stale (404) вызывающий сбрасывает
    кэш и повторяет один раз. Сбой -> None (fail-open, не исключение).
    Пейджинг ограничен (MAX_SESSION_PAGES): «Control top» — старая сессия,
    глубже уходить смысла нет; не найдена в пределах лимита -> None.
    """
    global _coord_session_id
    url = OPENCODE_ENDPOINT + "/api/session"
    for _ in range(MAX_SESSION_PAGES):
        rows, nxt = _page_sessions(tok, url)
        if rows is None:
            return None
        for s in rows:
            if isinstance(s, dict) and s.get("title") == COORD_TITLE:
                _coord_session_id = str(s.get("id") or "")
                return _coord_session_id or None
        if not nxt:
            return None
        url = (OPENCODE_ENDPOINT + "/api/session?cursor="
               + urllib.parse.quote(nxt, safe=""))
    return None


def wake_coord(row: dict):
    """fail-open wake: любой сбой -> (status, err), исключения не бросает.

    Статусы: "ok" | "failed" (wake_err — без секретов: токен только в
    заголовке в памяти, в URL/тексте ошибки его нет).
    """
    last_err = ""
    for attempt in (1, 2):
        if attempt == 2:
            global _coord_session_id
            _coord_session_id = None  # stale -> перерезолв один раз
        try:
            tok = _service_token()
            if not tok:
                return "failed", "no service token (%s)" % SERVICE_JSON
            sid = _coord_session_id or _resolve_coord_session(tok)
            if not sid:
                return "failed", (
                    "coordinator session not found (title %r)" % COORD_TITLE)
            text = (
                "TG topic 33: новое входящее id=%s from=%s date=%s. "
                "Реакция обязательна: прочитай журнал %s (tail) и ответь. "
                "Текст: %s"
                % (row.get("id"), row.get("from"), row.get("date"),
                   JOURNAL, (row.get("text_preview") or "(без текста)")[:PREVIEW])
            )
            req = urllib.request.Request(
                "%s/api/session/%s/prompt" % (OPENCODE_ENDPOINT, sid),
                data=json.dumps({"text": text}).encode(),
                headers={"Authorization": _basic_auth(tok),
                         "Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=WAKE_TIMEOUT) as r:
                r.read()
            # R7 (И-53): lineage-запись wake-parent — кто разбудил координатора
            try:
                import subprocess as _sp
                _sp.run(["python3",
                    "/home/rudra/dotfiles/tools/lineage/lineage.py", "append",
                    "--kind", "fact", "--session-id", sid,
                    "--edge", "wake-parent", "--via", "tg-guard",
                    "--ref", "tg-wake-%s" % row.get("id"),
                    "--note", "from=%s" % row.get("from")],
                    capture_output=True, timeout=5)
            except Exception:  # fail-open — lineage не блокирует wake
                pass
            return "ok", ""
        except Exception as e:  # noqa: BLE001 — fail-open по дизайну
            last_err = "%s: %s" % (type(e).__name__, e)
    return "failed", last_err


def main(argv):
    if "--help" in argv or "-h" in argv:
        print(USAGE)  # безвредно: до env, сети и сессии не доходим
        return 0
    topic = None
    known_vals = set()
    if "--topic" in argv:
        i = argv.index("--topic")
        if i + 1 >= len(argv):
            sys.exit("tg-guard: --topic без значения — отказ (см. --help)")
        topic = watch._int_or_exit("--topic", argv[i + 1])
        known_vals.add(argv[i + 1])
    allowed = {"--topic"} | known_vals
    stray = [a for a in argv if a not in allowed]
    if stray:
        sys.exit(f"tg-guard: неизвестные аргументы {stray} — отказ "
                 f"(см. --help)")
    if topic is None:
        sys.exit("tg-guard: нет --topic ID — отказ "
                 "(fail-closed, group-wide запрещён; см. --help)")
    if topic not in ALLOWED_TOPICS:
        sys.exit(f"tg-guard: topic {topic} вне разрешённого scope "
                 f"(разрешён: {sorted(ALLOWED_TOPICS)}) — отказ ДО env/сети "
                 f"(см. --help)")

    env = watch.load_env(watch.ENV_FILE)
    api_id = env.get("TG_API_ID", "")
    api_hash = env.get("TG_API_HASH", "")
    group = env.get("SSA_GROUP_ID", "")
    proxy = watch.tg_profile.parse_proxy(env.get("TG_PROXY", ""))
    if not api_id or not api_hash or not group:
        sys.exit("tg-guard: заполни TG_API_ID/TG_API_HASH/SSA_GROUP_ID в "
                 + watch.ENV_FILE)
    try:
        from telethon import TelegramClient, events
    except ImportError:
        sys.exit("tg-guard: нет telethon (владелец ставит: "
                 "pip install --user telethon)")
    try:
        import python_socks  # noqa: F401
    except ImportError:
        if proxy is not None:
            sys.exit("tg-guard: задан TG_PROXY, но нет python-socks "
                     "(владелец ставит: pip install --user "
                     "'python-socks[asyncio]')")

    session = watch.prepare_session(GUARD_SESSION_SUFFIX)

    async def run():
        seen = 0
        woken = 0
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:
                pass  # не-posix: дефолтное поведение сигнала

        async with TelegramClient(session, int(api_id), api_hash,
                                  proxy=proxy) as client:
            me = await client.get_me()
            ent = await client.get_entity(int(group))
            topics = await watch._topic_ids(client, ent)
            if topic not in topics:
                sys.exit(f"tg-guard: топика {topic} нет в группе "
                         f"(есть: {sorted(topics)}) — отказ")

            async def on_new_message(event):
                nonlocal seen, woken
                m = event.message
                # Фильтр топика в обработчике (как в ядре): наружу — только 33.
                if watch._thread_of(m) != topic:
                    return
                try:
                    row = await watch._row(client, m, topic)
                except Exception as e:  # noqa: BLE001 — одно сбойное
                    # сообщение не убивает цикл
                    sys.stderr.write(f"tg-guard: строка события не собрана "
                                     f"(id={getattr(m, 'id', '?')}, {e!r})\n")
                    return
                # Журнал ВСЕГДА (входящие + исходящие — аудит), прежде чем
                # что-либо сетевое: источник правды пишется первым.
                incoming = (row.get("from") or "") != OUR_USER
                entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                             time.gmtime()), **row}
                if incoming:
                    # wake best-effort, вне event-loop (urllib синхронный)
                    status, err = await loop.run_in_executor(
                        None, wake_coord, row)
                    entry["wake"] = status
                    if err:
                        entry["wake_err"] = err
                    if status == "ok":
                        woken += 1
                else:
                    entry["wake"] = "skipped"  # своё сообщение — только аудит
                try:
                    journal_append(entry)
                except Exception as e:  # noqa: BLE001
                    sys.stderr.write("tg-guard: ошибка журнала: %s: %s "
                                     "(демон продолжает)\n"
                                     % (type(e).__name__, e))
                seen += 1

            client.add_event_handler(
                on_new_message,
                events.NewMessage(chats=ent, incoming=True, outgoing=True))

            # Heartbeat + outage-visibility (инцидент tg-guard-journal-
            # silent-20261028): тишина стоража ≠ здоровье. Каждые 30с
            # состояние связи; 4 последовательных обрыва → outage-запись в
            # state профиля + exit(75) — systemd перезапустит с свежим env.
            outage_file = os.path.join(
                os.path.dirname(JOURNAL), "guard-outage.jsonl")
            fails = 0

            def _outage(reason):
                try:
                    os.makedirs(os.path.dirname(outage_file), exist_ok=True)
                    with open(outage_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps({
                            "ts": int(time.time()),
                            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                 time.gmtime()),
                            "class": "connection-outage",
                            "profile": "ssa", "topic": topic,
                            "reason": reason[:200]}, ensure_ascii=False) + "\n")
                except Exception:  # noqa: BLE001
                    pass

            async def heartbeat():
                nonlocal fails
                ticks = 0
                while True:
                    await asyncio.sleep(30)
                    ticks += 1
                    if not client.is_connected():
                        fails += 1
                        sys.stderr.write(
                            f"tg-guard: heartbeat: НЕТ СВЯЗИ ({fails}/4)\n")
                        if fails >= 4:
                            _outage(f"connection failed x{fails}")
                            sys.stderr.write(
                                "tg-guard: outage -> exit(75), systemd "
                                "перезапустит\n")
                            os._exit(75)
                    else:
                        if fails:
                            sys.stderr.write("tg-guard: связь восстановлена\n")
                        fails = 0
                    if ticks % 10 == 0:
                        sys.stderr.write(f"tg-guard: alive topic={topic} "
                                          f"connected={client.is_connected()}\n")

            hb = asyncio.create_task(heartbeat())

            sys.stderr.write(
                f"tg-guard: как {me.username or me.id} -> {group} "
                f"topic={topic}, журнал {JOURNAL}, wake fail-open -> "
                f"{OPENCODE_ENDPOINT} (сессия «{COORD_TITLE}»)\n")
            await stop.wait()
            await client.disconnect()
        sys.stderr.write(
            f"tg-guard: остановка (сигнал), событий={seen} woken={woken}\n")
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
