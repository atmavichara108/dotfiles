#!/usr/bin/env python3
"""trademind-tg-guard — постоянный push-сторож чата TradeMind «🧶Препарыночная🪢».

Долгоживущий демон (user-юнит trademind-tg-guard.service), исполнение
мандата Р-082: сторожа фиксирует меты-only и будит сессию TradeMind на вход;
обработка писем — сессия (примари — Служитель Обсидиан).

Профиль trademind (chat-scope): тот же Maya-аккаунт и env, что у portal —
права бота и членство остаются рукой владельца (Р-082), до них доступ через
Maya. Read-only: send/edit/delete в коде нет.

Дизайн (по образцу tg-guard/serp-tg-guard):
  - ядро = tg-watch.py с TG_PROFILE=trademind (push-слушатель, Telethon
    events.NewMessage, без поллинга, read-only) — импортируется как модуль,
    не копируется;
  - каждое сообщение чата (входящие + исходящие — аудит) — одна JSON-строка
    в append-only журнал ~/.local/state/trademind-tg/guard-journal.jsonl:
    метаданные + text_preview <= 200; без полного тела, без секретов;
  - на входящее (from != AllIsMaya) — wake сессии TradeMind:
    POST /api/session/<id>/prompt в локальный OpenCode-сервер
    (opencode-serve, 127.0.0.1:49374). Basic-auth токен читается из
    ~/.config/opencode/service.json и НИКОГДА не логируется/не выводится.

Wake — fail-open:
  - журнал пишется ВСЕГДА и первым; wake — best-effort;
  - сервер/сессия недоступны — событие не теряется (осталось в журнале):
    строка помечается wake="failed" + wake_err (без секретов);
  - повтор — одно перерезолвление/повторный POST, без слепых ретрай-циклов.

Безопасность:
  - target-session берём из env TRADEMIND_SESSION_ID (default — id носителя
    из Р-082), не из argv: сессии могут пересоздаваться;
  - --chat обязателен и без значения (группа из профиля trademind), неизвестный
    аргумент — отказ ДО env/сети;
  - секреты — только в ~/.config/portal-tg/tg.env и
    ~/.config/opencode/service.json; никогда в argv/журнале/логах.

Запуск (включает владелец):
  systemctl --user daemon-reload && systemctl --user enable --now trademind-tg-guard
Вручную: python3 trademind-tg-guard.py --chat
Остановка: SIGTERM/SIGINT — чистый exit.
"""
from __future__ import annotations

import os as _os
_os.environ["TG_PROFILE"] = "trademind"  # ДО импорта ядра: профиль читается при загрузке

import asyncio
import base64
import importlib.util
import json
import os
import signal
import sys
import time
import urllib.request

# --- ядро: tg-watch.py (импорт как модуль, без копирования кода) ----------
_HERE = os.path.dirname(os.path.abspath(__file__))
_SPEC = importlib.util.spec_from_file_location(
    "tg_watch_core", os.path.join(_HERE, "tg-watch.py"))
if _SPEC is None or _SPEC.loader is None:
    sys.exit("trademind-tg-guard: не удалось загрузить ядро tg-watch.py — отказ")
watch = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(watch)  # безопасно: main под __main__-гардом

JOURNAL_DIR = os.path.expanduser("~/.local/state/trademind-tg")
JOURNAL = os.path.join(JOURNAL_DIR, "guard-journal.jsonl")
GUARD_SESSION_SUFFIX = "-guard"
OUR_USER = _os.environ.get("TRADEMIND_OUR_USER", "AllIsMaya")
TARGET_SESSION = _os.environ.get("TRADEMIND_SESSION_ID",
                                  "ses_e779da1d9ffeYgFTk7C0sQ6qDI")
SERVICE_JSON = os.path.expanduser("~/.config/opencode/service.json")
OPENCODE_ENDPOINT = os.environ.get("OPENCODE_ENDPOINT",
                                  "http://127.0.0.1:49374")
OPENCODE_SERVICE_USER = os.environ.get("OPENCODE_SERVICE_USER", "opencode")
WAKE_TIMEOUT = 10.0
PREVIEW = 200

USAGE = """trademind-tg-guard --chat
Постоянный push-сторож чата TradeMind «🧶Препарыночная🪢» (chat-scope,
user-юнит trademind-tg-guard.service).
  --chat        сторож группы из профиля trademind (обязателен; не топик)
Журнал (append-only, единственный источник правды по событиям):
  ~/.local/state/trademind-tg/guard-journal.jsonl
  строка: {ts, id, topic, from, date, type, filename, mime, size, sha256,
           text_preview(<=200), wake: ok|failed|skipped[, wake_err]}
Wake (fail-open): на входящее (from != AllIsMaya) — POST /api/session/<id>/prompt
в локальный OpenCode-сервер (127.0.0.1:49374); сессия TradeMind — из env
TRADEMIND_SESSION_ID; токен — из ~/.config/opencode/service.json (нигде не
логируется). Сервер/сессия недоступны — событие остаётся в журнале с
wake="failed", демон продолжает слушать.
Read-only: send/edit/delete в коде нет. Секреты — только в env/service.json.
Запуск: python3 trademind-tg-guard.py --chat (или через юнит).
"""


def journal_append(entry: dict) -> None:
    """Одна JSON-строка в append-only журнал (dir 0700, file 0600, fsync)."""
    os.makedirs(JOURNAL_DIR, mode=0o700, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False)
    fd = os.open(JOURNAL, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def _load_seen_ids() -> set[int]:
    """id уже журналированных сообщений: рестарт не пишет дубль."""
    out: set[int] = set()
    if not os.path.exists(JOURNAL):
        return out
    try:
        with open(JOURNAL, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:  # noqa: BLE001 — битая строка не валит сторож
                    continue
                if isinstance(d, dict) and d.get("id") is not None:
                    try:
                        out.add(int(d["id"]))
                    except (TypeError, ValueError):
                        pass
    except OSError:
        pass
    return out


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


def wake_trademind(row: dict):
    """fail-open wake: любой сбой -> (status, err), исключения не бросает."""
    last_err = ""
    for _attempt in (1, 2):
        try:
            tok = _service_token()
            if not tok:
                return "failed", "no service token (%s)" % SERVICE_JSON
            sid = TARGET_SESSION
            if not sid:
                return "failed", "empty TRADEMIND_SESSION_ID"
            text = (
                "TG chat TradeMind (🧶Препарыночная🪢): новое входящее id=%s "
                "from=%s date=%s. Реакция обязательна: прочитай журнал %s "
                "(tail) и обработай письмо. Текст: %s"
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
            # R7 (И-53): след «кто разбудил сессию»
            try:
                import subprocess as _sp
                _sp.run(["python3",
                    "/home/rudra/dotfiles/tools/lineage/lineage.py", "append",
                    "--kind", "fact", "--session-id", sid,
                    "--edge", "wake-parent", "--via", "trademind-tg-guard",
                    "--ref", "tg-wake-trademind-%s" % row.get("id"),
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
    known = set()
    if "--chat" in argv:
        i = argv.index("--chat")
        if i + 1 < len(argv):
            sys.exit("trademind-tg-guard: --chat без значения — отказ "
                     "(см. --help)")
        known.add("--chat")
    if "--chat" not in known:
        sys.exit("trademind-tg-guard: нет --chat — отказ (fail-closed; "
                 "см. --help)")
    stray = [a for a in argv if a not in known]
    if stray:
        sys.exit(f"trademind-tg-guard: неизвестные аргументы {stray} — отказ "
                 f"(см. --help)")

    env = watch.load_env(watch.ENV_FILE)
    api_id = env.get("TG_API_ID", "")
    api_hash = env.get("TG_API_HASH", "")
    group = (env.get(watch._PROFILE["group_key"], "")
             or watch._PROFILE.get("group_default", ""))
    proxy = watch.tg_profile.parse_proxy(env.get("TG_PROXY", ""))
    if not api_id or not api_hash or not group:
        sys.exit("trademind-tg-guard: заполни TG_API_ID/TG_API_HASH/"
                 + watch._PROFILE["group_key"] + " (или group_default профиля) в "
                 + watch.ENV_FILE)
    try:
        from telethon import TelegramClient, events
    except ImportError:
        sys.exit("trademind-tg-guard: нет telethon (владелец ставит: "
                 "pip install --user telethon)")
    try:
        import python_socks  # noqa: F401
    except ImportError:
        if proxy is not None:
            sys.exit("trademind-tg-guard: задан TG_PROXY, но нет python-socks "
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
                pass

        async with TelegramClient(session, int(api_id), api_hash,
                                  proxy=proxy) as client:
            me = await client.get_me()
            ent = await client.get_entity(int(group))
            seen_ids = _load_seen_ids()

            async def on_new_message(event):
                nonlocal seen, woken
                m = event.message
                if m.id in seen_ids:
                    return
                seen_ids.add(m.id)
                try:
                    row = await watch._row(client, m, 0)
                except Exception as e:  # noqa: BLE001 — одно сбойное
                    sys.stderr.write(f"trademind-tg-guard: строка события не "
                                     f"собрана (id={getattr(m, 'id', '?')}, "
                                     f"{e!r})\n")
                    return
                # Журнал ВСЕГДА (входящие + исходящие — аудит), до сети.
                incoming = (row.get("from") or "") != OUR_USER
                entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                             time.gmtime()), **row}
                if incoming:
                    status, err = await loop.run_in_executor(
                        None, wake_trademind, row)
                    entry["wake"] = status
                    if err:
                        entry["wake_err"] = err
                    if status == "ok":
                        woken += 1
                else:
                    entry["wake"] = "skipped"
                try:
                    journal_append(entry)
                except Exception as e:  # noqa: BLE001
                    sys.stderr.write("trademind-tg-guard: ошибка журнала: "
                                     "%s: %s (демон продолжает)\n"
                                     % (type(e).__name__, e))
                seen += 1

            outage_file = os.path.join(JOURNAL_DIR, "guard-outage.jsonl")
            fails = 0

            def _outage(reason):
                try:
                    os.makedirs(JOURNAL_DIR, mode=0o700, exist_ok=True)
                    with open(outage_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps({
                            "ts": int(time.time()),
                            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                 time.gmtime()),
                            "class": "connection-outage",
                            "profile": "trademind",
                            "group": group,
                            "reason": reason[:200]}, ensure_ascii=False) + "\n")
                except Exception:  # noqa: BLE001
                    pass

            async def heartbeat():
                nonlocal fails
                ticks = 0
                while not stop.is_set():
                    await asyncio.sleep(30)
                    if stop.is_set():
                        return
                    ticks += 1
                    if not client.is_connected():
                        fails += 1
                        sys.stderr.write(
                            f"trademind-tg-guard: heartbeat: НЕТ СВЯЗИ "
                            f"({fails}/4) — события не идут\n")
                        if fails >= 4:
                            _outage(f"connection failed x{fails}")
                            sys.stderr.write(
                                "trademind-tg-guard: outage -> exit(75), "
                                "systemd перезапустит\n")
                            os._exit(75)
                    else:
                        if fails:
                            sys.stderr.write(
                                "trademind-tg-guard: связь восстановлена\n")
                        fails = 0
                    if ticks % 10 == 0:
                        sys.stderr.write(
                            f"trademind-tg-guard: alive chat connected="
                            f"{client.is_connected()} seen={seen} woken={woken}\n")

            asyncio.create_task(heartbeat())

            client.add_event_handler(
                on_new_message,
                events.NewMessage(chats=ent, incoming=True, outgoing=True))
            sys.stderr.write(
                f"trademind-tg-guard: как {me.username or me.id} -> {group} "
                f"chat=TradeMind, журнал {JOURNAL}, wake fail-open -> "
                f"{OPENCODE_ENDPOINT} (сессия {TARGET_SESSION})\n")
            await stop.wait()
            await client.disconnect()
        sys.stderr.write(
            f"trademind-tg-guard: остановка (сигнал), событий={seen} "
            f"woken={woken}\n")
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
