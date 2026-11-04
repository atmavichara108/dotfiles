#!/usr/bin/env python3
"""portal-tg-guard — постоянный push-сторож кабинета Капитанский портал (TG-весь чат (chat-scope)).

Долгоживущий демон (user-юнит portal-tg-guard.service), ЭТАП 2 мандата
portal-tg-gateway (слово владельца 2026-10-24 «делай»). По образцу tg-guard.py,
профиль dv: TG_PROFILE=portal выставляется ДО импорта ядра tg-watch.
Отличия: env ~/.config/portal-tg/tg.env, guard-сессия dv-guard.session, журнал
~/.local/state/portal-tg/guard-journal.jsonl, wake fail-open в сессию координатора
(название из DV_WAKE_SESSION_TITLE, умолчание «Control top»), тег канала
portal-tg в lineage. Read-only: send/edit/delete в коде нет.

Дизайн (апрув владельца 2026-10-18; конвенция — control/docs/tg-comms-rules.md,
раздел «Постоянный канал tg-guard»):
  - ядро = tg-watch.py с TG_PROFILE=portal (push-слушатель, Telethon events.NewMessage, без
    поллинга, read-only) — импортируется как модуль, не копируется;
  - каждое сообщение чата (входящие + исходящие, для аудита) — одна
    JSON-строка в append-only журнал
    ~/.local/state/portal-tg/guard-journal.jsonl: метаданные + text_preview
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
  - --topic строго из scope профиля (dv: {}), неизвестный аргумент — отказ
    ДО env/сети (rc=1);
  - секреты (TG_API_ID/TG_API_HASH, service-токен) — только в
    ~/.config/portal-tg/tg.env и ~/.config/opencode/service.json; никогда в
    argv, журнале, логах;
  - собственная копия сессии ssa-guard.session (второй легитимный логин
    того же аккаунта) — как в tg-watch;
  - wake-ошибка: один повтор с перерезолвом сессии; без слепых ретрай-циклов
    (следующее входящее попробует снова).

Запуск: user-юнит portal-tg-guard.service (Restart=always); активация — владельцем:
  systemctl --user daemon-reload && systemctl --user enable --now portal-tg-guard
Вручную: python3 portal-tg-guard.py --topic N (в портале топиков нет)
Остановка: SIGTERM/SIGINT — чистый exit.
"""
from __future__ import annotations

import os as _os
_os.environ["TG_PROFILE"] = "portal"  # ДО импорта ядра: профиль читается при загрузке

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
    sys.exit("portal-tg-guard: не удалось загрузить ядро tg-watch.py — отказ")
watch = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(watch)  # безопасно: main под __main__-гардом

_MSK = watch._MSK  # время корабля — МСК (слово владельца)

JOURNAL_DIR = os.path.expanduser("~/.local/state/portal-tg")
JOURNAL = os.path.join(JOURNAL_DIR, "guard-journal.jsonl")
GUARD_SESSION_SUFFIX = "-guard"

# --- вторая линия: бета-группа M Code (отдел движков) --------------------
# Слово владельца 2026-11-04: «вступить и на автомате подхватывать обновления,
# отправлять багрепорты». Будить только на релизы/объявления от админов,
# ответы на наши сообщения и упоминания; остальное — тихий журнал (метаданные).
BETA_CHAT_ID = int(_os.environ.get("MCODE_BETA_CHAT_ID", "-1004383334504"))
BETA_JOURNAL_DIR = os.path.expanduser("~/.local/state/mcode-beta")
BETA_JOURNAL = os.path.join(BETA_JOURNAL_DIR, "journal.jsonl")
BETA_STATE = os.path.join(BETA_JOURNAL_DIR, "state.json")
BETA_OUR_USER = "AllIsMaya"
BETA_PREVIEW = 300
BETA_ADMINS: set[int] = set()
OUR_USER = _os.environ.get("DV_OUR_USER", "Atma_Vichara108")
COORD_SID = _os.environ.get("TG_WAKE_SESSION_ID", "")  # прямой sid зова (если задан)
COORD_TITLE = (_os.environ.get("TG_WAKE_SESSION_TITLE")
                 or _os.environ.get("DV_WAKE_SESSION_TITLE")
                 or "Control top")
SERVICE_JSON = os.path.expanduser("~/.config/opencode/service.json")
OPENCODE_ENDPOINT = os.environ.get("OPENCODE_ENDPOINT",
                                   "http://127.0.0.1:49374")
OPENCODE_SERVICE_USER = os.environ.get("OPENCODE_SERVICE_USER", "opencode")
WAKE_TIMEOUT = 10.0
PREVIEW = 200
ALLOWED_TOPICS = watch.ALLOWED_TOPICS  # {33} — строже, из ядра

USAGE = """portal-tg-guard --topic N (в портале топиков нет)
Постоянный push-сторож кабинета Капитанский портал — весь чат (chat-scope) (user-юнит portal-tg-guard.service).
  --topic ID        ID форумного топика (обязателен; вне scope профиля — отказ
                    ДО env/сети)
Журнал (append-only, единственный источник правды по событиям):
  ~/.local/state/portal-tg/guard-journal.jsonl
  строка: {ts, id, topic, from, date, type, filename, mime, size, sha256,
           text_preview(<=200), wake: ok|failed|skipped[, wake_err]}
Wake (fail-open): на входящее (from != %s) — POST /api/session/<id>/prompt (fail-open)
в локальный OpenCode-сервер (%s по умолчанию, переопределение env
OPENCODE_ENDPOINT); сессия координатора — по названию «%s»; токен — из
~/.config/opencode/service.json (нигде не логируется). Сервер/сессия
недоступны — событие остаётся в журнале с wake="failed", демон продолжает
слушать; реакция по журналу при следующей сессии.
Read-only: send/edit/delete в коде нет. Секреты — только в env/service.json.
Запуск: python3 portal-tg-guard.py --topic N (в портале топиков нет) (или через юнит).
""" % (OUR_USER, OPENCODE_ENDPOINT, COORD_TITLE)


def journal_append(entry: dict, path: str | None = None) -> None:
    """Одна JSON-строка в append-only журнал (dir 0700, file 0600, fsync)."""
    path = path or JOURNAL
    dirpath = os.path.dirname(path)
    os.makedirs(dirpath, mode=0o700, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def _load_seen_ids(path: str) -> set[int]:
    """id уже отражённых сообщений из хвоста журнала (для досмотра)."""
    seen: set[int] = set()
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()[-2000:]
        for line in lines:
            try:
                mid = json.loads(line).get("id")
                if isinstance(mid, int):
                    seen.add(mid)
            except Exception:  # noqa: BLE001 — битая строка не повод падать
                continue
    except Exception:  # noqa: BLE001 — нет журнала = пусто
        pass
    return seen


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
            sid = COORD_SID or _coord_session_id or _resolve_coord_session(tok)
            if not sid:
                return "failed", (
                    "coordinator session not found (title %r)" % COORD_TITLE)
            text = (
                "TG portal (Капитанский портал): новое входящее id=%s from=%s date=%s "
                "topic=%s reply_to=%s quote=%s. Реакция обязательна: прочитай журнал %s "
                "(tail) и ответь. Текст: %s"
                % (row.get("id"), row.get("from"),
                   row.get("date_msk") or row.get("date"),
                   row.get("topic"), row.get("reply_to_msg_id") or "-",
                   row.get("quote_text") or "-",
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
                    "--edge", "wake-parent", "--via", "portal-tg-guard",
                    "--ref", "tg-wake-dv-%s" % row.get("id"),
                    "--note", "from=%s" % row.get("from")],
                    capture_output=True, timeout=5)
            except Exception:  # fail-open — lineage не блокирует wake
                pass
            return "ok", ""
        except Exception as e:  # noqa: BLE001 — fail-open по дизайну
            last_err = "%s: %s" % (type(e).__name__, e)
    return "failed", last_err


# --- бета-группа M Code: обработчик второй линии --------------------------

_RELEASE_RE = None  # ленивая инициализация (re импортируется ниже)


def _release_re():
    global _RELEASE_RE
    if _RELEASE_RE is None:
        import re as _re
        _RELEASE_RE = _re.compile(
            r"(1\.\d+\.\d+|верси|релиз|обновлен|changelog|AppImage|\.dmg|\.exe"
            r"|сборк|нов(ая|ое) верси)", _re.IGNORECASE)
    return _RELEASE_RE


def _post_prompt(text: str, ref: str) -> tuple[str, str]:
    """POST /api/session/<id>/prompt (fail-open, исключения не бросает)."""
    last_err = ""
    for attempt in (1, 2):
        if attempt == 2:
            global _coord_session_id
            _coord_session_id = None
        try:
            tok = _service_token()
            if not tok:
                return "failed", "no service token (%s)" % SERVICE_JSON
            sid = COORD_SID or _coord_session_id or _resolve_coord_session(tok)
            if not sid:
                return "failed", (
                    "coordinator session not found (title %r)" % COORD_TITLE)
            req = urllib.request.Request(
                "%s/api/session/%s/prompt" % (OPENCODE_ENDPOINT, sid),
                data=json.dumps({"text": text}).encode(),
                headers={"Authorization": _basic_auth(tok),
                         "Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=WAKE_TIMEOUT) as r:
                r.read()
            try:
                import subprocess as _sp
                _sp.run(["python3",
                    "/home/rudra/dotfiles/tools/lineage/lineage.py", "append",
                    "--kind", "fact", "--session-id", sid,
                    "--edge", "wake-parent", "--via", "mcode-beta-guard",
                    "--ref", ref, "--note", "beta-group"],
                    capture_output=True, timeout=5)
            except Exception:  # fail-open — lineage не блокирует wake
                pass
            return "ok", ""
        except Exception as e:  # noqa: BLE001 — fail-open по дизайну
            last_err = "%s: %s" % (type(e).__name__, e)
    return "failed", last_err


def _beta_state_load() -> dict:
    try:
        with open(BETA_STATE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("my_ids"), list):
            return {"my_ids": [int(x) for x in data["my_ids"]][-500:]}
    except Exception:  # noqa: BLE001 — нет состояния = пусто
        pass
    return {"my_ids": []}


def _beta_state_save(state: dict) -> None:
    try:
        os.makedirs(BETA_JOURNAL_DIR, mode=0o700, exist_ok=True)
        fd = os.open(BETA_STATE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"my_ids": state.get("my_ids", [])[-500:]}, f)
    except Exception as e:  # noqa: BLE001 — состояние не критично
        sys.stderr.write("portal-tg-guard: beta state не сохранён: %r\n" % (e,))


def _looks_like_announcement(m) -> bool:
    """Объявление/релиз от админа: закреп, вложение-сборка, маркеры версии."""
    if getattr(m, "pinned", False):
        return True
    if getattr(m, "document", None) is not None:
        return True
    text = m.text or ""
    if len(text) >= 180:
        return True
    return bool(text) and _release_re().search(text) is not None


def _mentions_us(m) -> bool:
    text = m.text or ""
    if "@allismaya" in text.lower():
        return True
    for e in (getattr(m, "entities", None) or []):
        if type(e).__name__ == "MessageEntityMention":
            try:
                if text[e.offset:e.offset + e.length].lower() == "@allismaya":
                    return True
            except Exception:  # noqa: BLE001
                pass
    return False


def make_beta_handler(client, ent, journal_path: str):
    """Обработчик второй линии: тихий журнал + точечный wake."""
    state = _beta_state_load()
    my_ids = set(state["my_ids"])
    beta_seen = _load_seen_ids(journal_path)
    beta_ready = asyncio.Event()

    async def handle_beta(m):
        if m.id in beta_seen:
            return
        beta_seen.add(m.id)
        try:
            rt = getattr(m, "reply_to", None)
            reply_to = getattr(rt, "reply_to_msg_id", None)
            row = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "id": m.id,
                "chat": "mcode-beta",
                "date": m.date.isoformat() if m.date else "",
                "date_msk": (m.date.astimezone(_MSK).strftime("%Y-%m-%d %H:%M МСК")
                             if m.date else ""),
                "sender_id": getattr(m, "sender_id", None),
                "out": bool(getattr(m, "out", False)),
                "type": ("text" if m.text and not getattr(m, "media", None)
                         else ("file" if getattr(m, "media", None) else "text")),
                "size": len(m.text or ""),
                "reply_to_msg_id": reply_to,
            }
            try:
                s = await m.get_sender()
                row["from"] = (getattr(s, "username", None)
                               or getattr(s, "first_name", None) or "")
            except Exception:  # noqa: BLE001
                row["from"] = ""

            if row["out"]:
                my_ids.add(m.id)
                state["my_ids"] = list(my_ids)
                _beta_state_save(state)
                row["wake"] = "skipped"
                journal_append(row, journal_path)
                return

            reasons = []
            if getattr(m, "pinned", False):
                reasons.append("pinned")
            if row["sender_id"] in BETA_ADMINS:
                if _looks_like_announcement(m):
                    reasons.append("release")
            if reply_to is not None and int(reply_to) in my_ids:
                reasons.append("reply_to_us")
            if _mentions_us(m):
                reasons.append("mention")

            if not reasons:
                row["wake"] = "quiet"
                journal_append(row, journal_path)
                return

            row["reason"] = ",".join(reasons)
            row["text_preview"] = (m.text or "")[:BETA_PREVIEW]
            text = (
                "M Code beta (группа Beta Test | M Code): id=%s from=%s date=%s "
                "reason=%s reply_to=%s. Прочитай сообщение и реши: багрепорт, "
                "ответ или тишина. Журнал: %s. Текст: %s"
                % (m.id, row.get("from") or row["sender_id"], row["date"],
                   row["reason"], reply_to or "-", journal_path,
                   (m.text or "(без текста)")[:BETA_PREVIEW])
            )
            loop = asyncio.get_running_loop()
            status, err = await loop.run_in_executor(
                None, _post_prompt, text, "mcode-beta-%s" % m.id)
            row["wake"] = status
            if err:
                row["wake_err"] = err
            journal_append(row, journal_path)
        except Exception as e:  # noqa: BLE001 — одно сбойное сообщение не валит цикл
            sys.stderr.write(
                "portal-tg-guard: beta-строка не собрана (id=%s, %r)\n"
                % (getattr(m, "id", "?"), e))

    async def on_beta_message(event):
        await handle_beta(event.message)

    async def sync_beta():
        """Досмотр второй линии: сверка чата с журналом, без пачек зовов."""
        await beta_ready.wait()  # история засеяна — старьё не будим
        while True:
            await asyncio.sleep(30)
            try:
                msgs = await client.get_messages(ent, limit=50)
                for m in sorted((x for x in msgs if x.id not in beta_seen),
                                key=lambda x: x.id):
                    await handle_beta(m)
            except Exception as e:  # noqa: BLE001 — досмотр не валит демон
                sys.stderr.write("portal-tg-guard: beta досмотр сбой: %r\n" % (e,))

    async def seed_my_ids():
        try:
            async for m in client.iter_messages(ent, limit=100):
                beta_seen.add(m.id)  # история = уже учтено, не будим
                if getattr(m, "out", False):
                    my_ids.add(m.id)
            state["my_ids"] = list(my_ids)
            _beta_state_save(state)
        except Exception as e:  # noqa: BLE001
            sys.stderr.write("portal-tg-guard: beta seed не удался: %r\n" % (e,))
        finally:
            beta_ready.set()

    async def refresh_admins():
        from telethon.tl.functions.channels import GetParticipantsRequest
        from telethon.tl.types import ChannelParticipantsAdmins
        while True:
            try:
                res = await client(GetParticipantsRequest(
                    channel=ent, filter=ChannelParticipantsAdmins(),
                    offset=0, limit=100, hash=0))
                BETA_ADMINS.clear()
                BETA_ADMINS.update(u.id for u in (res.users or []))
                sys.stderr.write(
                    "portal-tg-guard: beta admins=%d\n" % len(BETA_ADMINS))
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(
                    "portal-tg-guard: beta admins не получены: %r\n" % (e,))
            await asyncio.sleep(1800)

    return on_beta_message, seed_my_ids, refresh_admins, sync_beta


def main(argv):
    if "--help" in argv or "-h" in argv:
        print(USAGE)  # безвредно: до env, сети и сессии не доходим
        return 0
    topic = None
    known_vals = set()
    if "--topic" in argv:
        i = argv.index("--topic")
        if i + 1 >= len(argv):
            sys.exit("portal-tg-guard: --topic без значения — отказ (см. --help)")
        topic = watch._int_or_exit("--topic", argv[i + 1])
        known_vals.add(argv[i + 1])
    allowed = {"--topic"} | known_vals
    stray = [a for a in argv if a not in allowed]
    if stray:
        sys.exit(f"portal-tg-guard: неизвестные аргументы {stray} — отказ "
                 f"(см. --help)")
    if topic is None:
        sys.exit("portal-tg-guard: нет --topic ID — отказ "
                 "(fail-closed, group-wide запрещён; см. --help)")
    chat_scope = bool(watch._PROFILE.get("chat_scope"))
    if not chat_scope and topic not in ALLOWED_TOPICS:
        sys.exit(f"portal-tg-guard: topic {topic} вне разрешённого scope "
                 f"(разрешён: {sorted(ALLOWED_TOPICS)}) — отказ ДО env/сети "
                 f"(см. --help)")

    env = watch.load_env(watch.ENV_FILE)
    api_id = env.get("TG_API_ID", "")
    api_hash = env.get("TG_API_HASH", "")
    group = env.get(watch._PROFILE["group_key"], "")
    proxy = watch.tg_profile.parse_proxy(env.get("TG_PROXY", ""))
    if not api_id or not api_hash or not group:
        sys.exit("portal-tg-guard: заполни TG_API_ID/TG_API_HASH/SSA_GROUP_ID в "
                 + watch.ENV_FILE)
    try:
        from telethon import TelegramClient, events
    except ImportError:
        sys.exit("portal-tg-guard: нет telethon (владелец ставит: "
                 "pip install --user telethon)")
    try:
        import python_socks  # noqa: F401
    except ImportError:
        if proxy is not None:
            sys.exit("portal-tg-guard: задан TG_PROXY, но нет python-socks "
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
            if not chat_scope:
                topics = await watch._topic_ids(client, ent)
                if topic not in topics:
                    sys.exit(f"portal-tg-guard: топика {topic} нет в группе "
                             f"(есть: {sorted(topics)}) — отказ")

            portal_seen = _load_seen_ids(JOURNAL)

            async def handle_portal(m, allow_wake=True):
                """Одна обработка сообщения портала (push и досмотр — одна логика)."""
                nonlocal seen, woken
                if m.id in portal_seen:
                    return None
                portal_seen.add(m.id)
                # Фильтр топика в обработчике (как в ядре): chat-scope — весь чат,
                # форум-профили — только свой топик.
                if not chat_scope and watch._thread_of(m) != topic:
                    return None
                try:
                    row = await watch._row(client, m, topic)
                except Exception as e:  # noqa: BLE001 — одно сбойное
                    # сообщение не убивает цикл
                    sys.stderr.write(f"portal-tg-guard: строка события не собрана "
                                     f"(id={getattr(m, 'id', '?')}, {e!r})\n")
                    return None
                # Журнал ВСЕГДА (входящие + исходящие — аудит), прежде чем
                # что-либо сетевое: источник правды пишется первым.
                incoming = (row.get("from") or "") != OUR_USER
                if chat_scope:
                    # Жёсткая граница портала: чужие пишутся только в
                    # журнал; зов координатора — ТОЛЬКО от владельца.
                    incoming = (row.get("from") or "") == OUR_USER
                entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                             time.gmtime()), **row}
                if incoming and allow_wake:
                    # wake best-effort, вне event-loop (urllib синхронный)
                    status, err = await loop.run_in_executor(
                        None, wake_coord, row)
                    entry["wake"] = status
                    if err:
                        entry["wake_err"] = err
                    if status == "ok":
                        woken += 1
                elif incoming:
                    entry["wake"] = "catchup"  # зов уйдёт сводкой
                else:
                    entry["wake"] = "skipped"  # своё сообщение — только аудит
                try:
                    journal_append(entry)
                except Exception as e:  # noqa: BLE001
                    sys.stderr.write("portal-tg-guard: ошибка журнала: %s: %s "
                                     "(демон продолжает)\n"
                                     % (type(e).__name__, e))
                seen += 1
                return entry if incoming else None

            async def on_new_message(event):
                await handle_portal(event.message)

            async def sync_portal():
                """Досмотр: push-события теряются (INC-23) — сверяем чат с журналом."""
                while True:
                    await asyncio.sleep(20)
                    try:
                        msgs = await client.get_messages(ent, limit=50)
                        new = sorted((m for m in msgs
                                      if m.id not in portal_seen), key=lambda x: x.id)
                        if not new:
                            continue
                        rows = []
                        for m in new:  # хронологически, без зова
                            r = await handle_portal(m, allow_wake=False)
                            if r:
                                rows.append(r)
                        sys.stderr.write(
                            "portal-tg-guard: досмотр дотянул %d сообщ.\n" % len(new))
                        if rows:  # один сводный зов вместо пачки
                            ids = ", ".join(str(r.get("id")) for r in rows)
                            head = "; ".join(
                                "#%s %s: %s" % (r.get("id"),
                                                r.get("from") or "?",
                                                (r.get("text_preview") or "")[:120])
                                for r in rows[:8])
                            status, err = await loop.run_in_executor(
                                None, _post_prompt,
                                "TG portal (Капитанский портал): досмотр дотянул "
                                "пропущенное — id=%s. Реакция обязательна: прочитай "
                                "журнал %s (tail) и ответь. Содержимое: %s"
                                % (ids, JOURNAL, head),
                                "portal-catchup-%s" % rows[-1].get("id"))
                            sys.stderr.write(
                                "portal-tg-guard: досмотр wake=%s %s\n"
                                % (status, err or ""))
                    except Exception as e:  # noqa: BLE001 — досмотр не валит демон
                        sys.stderr.write(
                            "portal-tg-guard: досмотр сбой: %r\n" % (e,))

            # Heartbeat + outage (инцидент tg-guard-journal-silent-20261028)
            outage_file = os.path.join(
                os.path.dirname(JOURNAL), "guard-outage.jsonl")
            fails_dv = 0

            def _outage_dv(reason):
                try:
                    os.makedirs(os.path.dirname(outage_file), exist_ok=True)
                    with open(outage_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps({
                            "ts": int(time.time()),
                            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                 time.gmtime()),
                            "class": "connection-outage",
                            "profile": "dv", "topic": topic,
                            "reason": reason[:200]}, ensure_ascii=False) + "\n")
                except Exception:  # noqa: BLE001
                    pass

            async def heartbeat_dv():
                nonlocal fails_dv
                ticks = 0
                while True:
                    await asyncio.sleep(30)
                    ticks += 1
                    if not client.is_connected():
                        fails_dv += 1
                        sys.stderr.write(
                            f"portal-tg-guard: heartbeat: НЕТ СВЯЗИ ({fails_dv}/4)\n")
                        if fails_dv >= 4:
                            _outage_dv(f"connection failed x{fails_dv}")
                            sys.stderr.write(
                                "portal-tg-guard: outage -> exit(75), systemd "
                                "перезапустит\n")
                            os._exit(75)
                    else:
                        if fails_dv:
                            sys.stderr.write(
                                "portal-tg-guard: связь восстановлена\n")
                        fails_dv = 0
                    if ticks % 10 == 0:
                        sys.stderr.write(
                            f"portal-tg-guard: alive topic={topic} "
                            f"connected={client.is_connected()}\n")

            asyncio.create_task(heartbeat_dv())
            asyncio.create_task(sync_portal())

            # --- вторая линия: бета-группа M Code (best-effort, портал не страдает)
            try:
                beta_ent = await client.get_entity(BETA_CHAT_ID)
                handler, seed, admins, beta_sync = make_beta_handler(
                    client, beta_ent, BETA_JOURNAL)
                client.add_event_handler(
                    handler,
                    events.NewMessage(chats=beta_ent, incoming=True,
                                      outgoing=True))
                asyncio.create_task(seed())
                asyncio.create_task(admins())
                asyncio.create_task(beta_sync())
                sys.stderr.write(
                    "portal-tg-guard: beta -> %s (%s), журнал %s\n"
                    % (getattr(beta_ent, "title", "?"), beta_ent.id,
                       BETA_JOURNAL))
            except Exception as e:  # noqa: BLE001 — линия портала важнее
                sys.stderr.write(
                    "portal-tg-guard: beta не подключена: %r\n" % (e,))

            client.add_event_handler(
                on_new_message,
                events.NewMessage(chats=ent, incoming=True, outgoing=True))
            sys.stderr.write(
                f"portal-tg-guard: как {me.username or me.id} -> {group} "
                f"topic={topic}, журнал {JOURNAL}, wake fail-open -> "
                f"{OPENCODE_ENDPOINT} (сессия «{COORD_TITLE}»)\n")
            await stop.wait()
            await client.disconnect()
        sys.stderr.write(
            f"portal-tg-guard: остановка (сигнал), событий={seen} woken={woken}\n")
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
