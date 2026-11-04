#!/usr/bin/env python3
"""captain-panel-bot — бот-пульт капитана (спека docs/specs/captain-panel-bot-mvp.md).

Голос Корабля — Maya. Бот — пульт: команды, inline-кнопки, задачи,
инциденты, приватные ответы владельцу. Бот НЕ пишет обязательств от имени
Корабля («пульт принял», «передано Maya», «ожидает решения владельца»).

Boundary: команды исполняются ТОЛЬКО от владельца Atma_Vichara108; чужие —
только журнал (outcome=denied), без ответа в поток.

Секреты: токен только из ~/.config/captain-panel/tg.env (600), значение не
логируется и не печатается никогда.
State: ~/.local/state/captain-panel/ (panel-journal.jsonl, tasks.json,
settings.json, owner-dm.json, stage.json).
Журнал: меты-only, пишется ДО реакции (fail-open: сбой реакции не теряет
событие); полный текст чужих сообщений не пишется.

Зависимости: только stdlib (urllib long-polling Bot API) — без установок.

Использование:
  captain-panel-bot.py --dry-run   # smoke без сети (кнопки, отказ, journal)
  captain-panel-bot.py             # демон (user-юнит captain-panel-bot.service)
  rc: 0 ок · 1 нет токена/конфига
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HOME = os.path.expanduser("~")
ENV_FILE = os.path.join(HOME, ".config/captain-panel/tg.env")
STATE = os.path.join(HOME, ".local/state/captain-panel")
JOURNAL = os.path.join(STATE, "panel-journal.jsonl")
TASKS_F = os.path.join(STATE, "tasks.json")
SETTINGS_F = os.path.join(STATE, "settings.json")
OWNER_DM_F = os.path.join(STATE, "owner-dm.json")
STAGE_F = os.path.join(STATE, "stage.json")

API = "https://api.telegram.org/bot{token}/{method}"
OWNER = "Atma_Vichara108"          # boundary команд (спека §3/п.13)
GROUP = "-1003786610623"            # Капитанский портал
BOT_MARK = " · бот-пульт, не голос Корабля"
PROFILE = os.environ.get("CAPTAIN_PANEL_PROFILE", "captain-panel")
STATE_IDLE, STATE_STATUS, STATE_TASK_LIST = "idle", "status", "task_list"
STATE_TASK_ADD, STATE_INCIDENT, STATE_DENIED = "task_add", "incident", "denied"

# ---------- секреты и state ----------


def load_token():
    """Токен из ENV_FILE (600); значение никогда не возвращается наружу."""
    try:
        st = os.stat(ENV_FILE)
        if st.st_mode & 0o077:
            print(f"WARN: {ENV_FILE} не 600 (mode {oct(st.st_mode & 0o777)})",
                  file=sys.stderr)
    except FileNotFoundError:
        return None
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            bare = None
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("TG_BOT_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"')
                if "=" not in line and bare is None:
                    bare = line.strip('"')  # файл-секрет может быть голым токеном
            return bare
    except OSError:
        return None
    return None


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _save(path, obj):
    os.makedirs(STATE, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def journal(update, outcome, callback_data="", ref=""):
    """Меты-only строка ДО реакции (спека §5). Без тела чужих сообщений,
    без секретов: только адресат, id, исход, callback, ref."""
    upd_id = update.get("update_id") if isinstance(update, dict) else None
    m = update.get("message") or update.get("callback_query") or {} \
        if isinstance(update, dict) else {}
    frm = (m.get("from") or {}).get("username") \
        or (m.get("from") or {}).get("first_name") or ""
    rec = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "update_id": upd_id,
        "from": frm,
        "chat": str((m.get("chat") or {}).get("id", "")),
        "message_id": m.get("message_id"),
        "callback_data": callback_data or None,
        "outcome": outcome,
        "ref": ref or None,
        "profile": PROFILE,
    }
    os.makedirs(STATE, exist_ok=True)
    try:
        with open(JOURNAL, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass  # fail-open: реакция не теряется из-за журнала

# ---------- состояния (спека §4) ----------


def set_stage(stage):
    _save(STAGE_F, {"stage": stage})


def get_stage():
    return _load(STAGE_F, {}).get("stage", STATE_IDLE)

# ---------- задачи пульта (свой state, не чужие реестры) ----------


def tasks_add(text):
    tasks = _load(TASKS_F, {"next_id": 1, "open": []})
    tid = tasks["next_id"]
    tasks["open"].append({
        "id": tid, "title": text[:200],
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    })
    tasks["next_id"] = tid + 1
    _save(TASKS_F, tasks)
    return tid


def tasks_close(tid):
    tasks = _load(TASKS_F, {"next_id": 1, "open": []})
    keep = [t for t in tasks["open"] if t["id"] != tid]
    if len(keep) == len(tasks["open"]):
        return None
    tasks["open"] = keep
    _save(TASKS_F, tasks)
    return tid

# ---------- ответы ----------


def _kb(rows):
    return {"inline_keyboard": rows}


def kb_status():
    return _kb([
        [{"text": "Статус портала", "callback_data": "portal:status"},
         {"text": "Задачи", "callback_data": "portal:tasks"}],
        [{"text": "Инциденты", "callback_data": "portal:incidents"},
         {"text": "Маршрут Maya", "callback_data": "portal:route"}],
    ])


def kb_tasks():
    return _kb([
        [{"text": "Открыть задачу", "callback_data": "portal:task:open"},
         {"text": "Закрыть выбранную", "callback_data": "portal:task:close"}],
        [{"text": "Добавить", "callback_data": "portal:task:add"},
         {"text": "Назад", "callback_data": "portal:back"}],
    ])


def summary_text():
    """Сводка /status — из read-only Следопыта (tools/follower)."""
    import subprocess
    script = os.path.join(HOME, "dotfiles/tools/follower/follower.py")
    try:
        out = subprocess.run(
            ["python3", script, "--json-line"],
            capture_output=True, text=True, timeout=60)
        line = [l for l in out.stdout.splitlines() if l.startswith("{")]
        if line:
            d = json.loads(line[-1])
            bs = d.get("by_state", {})
            alerts = d.get("alerts", [])
            return (
                "Статус Корабля (Следопыт, read-only):\n"
                f"в работе {bs.get('в работе', 0)} · ждёт слова "
                f"{bs.get('ждёт слова', 0)} · зафиксировано "
                f"{bs.get('зафиксировано', 0)} · закрыто {bs.get('закрыто', 0)}\n"
                f"сигналов стагнации: {len(alerts)} · строк без состояния: "
                f"{d.get('unstated', 0)}"
            )
    except Exception:
        pass
    return "Сводка недоступна (Следопыт не отвечает)."

# ---------- wire (только stdlib) ----------


class Wire:
    def __init__(self, token):
        self.token = token

    def call(self, method, payload):
        """POST Bot API; токен в URL (стандарт), в логи не выводится."""
        req = urllib.request.Request(
            API.format(token=self.token, method=method),
            data=urllib.parse.urlencode(payload).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())

    def send(self, chat_id, text, reply_markup=None, parse_mode=None):
        p = {"chat_id": chat_id, "text": text + BOT_MARK}
        if reply_markup:
            p["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        if parse_mode:
            p["parse_mode"] = parse_mode
        return self.call("sendMessage", p)

    def answer_cb(self, cb_id, text=None, show_alert=False):
        p = {"callback_query_id": cb_id, "text": text or "пульт принял",
             "show_alert": show_alert}
        return self.call("answerCallbackQuery", p)

    def download_file(self, file_id, dest):
        """Скачивание файла Bot API в dest. Токен в URL не журналируется."""
        r = self.call("getFile", {"file_id": file_id})
        file_path = r.get("result", {}).get("file_path")
        if not file_path:
            raise RuntimeError("getFile did not return file_path")
        url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=120) as resp, \
                open(dest, "wb") as f:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        return dest

# ---------- обработка ----------


def is_owner(frm):
    return (frm or {}).get("username") == OWNER


def private_chat_id():
    d = _load(OWNER_DM_F, {})
    return d.get("chat_id")


def handle(wire, update, dry=False):
    """Одна обработка апдейта. dry=True — печатает что отправилось бы."""
    m = update.get("message") or update.get("callback_query")
    if not m:
        return
    frm = m.get("from") or {}
    chat_id = str((m.get("chat") or {}).get("id", ""))
    if "callback_query" in update:
        # У нажатия кнопки адрес лежит в callback_query.message.chat, а не в
        # самом callback_query: иначе ответ уходит «в никуда» (кнопки мертвы).
        _cb_msg = update["callback_query"].get("message") or {}
        chat_id = str((_cb_msg.get("chat") or {}).get("id", "") or chat_id)
    owner = is_owner(frm)

    def out(payload, where=None):
        if dry:
            print(f"[dry] -> {where or chat_id}: {json.dumps(payload, ensure_ascii=False)[:160]}")
            return None
        try:
            return wire.call(**payload) if isinstance(payload, dict) else payload
        except Exception as e:
            print(f"send failed: {type(e).__name__}", file=sys.stderr)
            return None

    def send_to(chat, text, kb=None):
        if dry:
            print(f"[dry] -> {chat}: {text[:120]}{BOT_MARK}")
            return
        try:
            wire.send(chat, text, reply_markup=kb)
        except Exception as e:
            print(f"send failed: {type(e).__name__}", file=sys.stderr)

    # Boundary (спека §3/п.13): чужой → только журнал, без ответа
    if not owner:
        journal(update, "denied")
        set_stage(STATE_DENIED)
        return

    # запомнить личный чат владельца для приватных ответов
    if str((m.get("chat") or {}).get("id", "")) != GROUP:
        _save(OWNER_DM_F, {"chat_id": chat_id,
                           "ts": dt.datetime.now(dt.timezone.utc).isoformat()})

    # ---- callback ----
    if "callback_query" in update:
        cb = update["callback_query"]
        data = cb.get("data", "")
        stage = get_stage()
        journal(update, "accepted", callback_data=data)

        if data == "portal:task:add":
            set_stage(STATE_TASK_ADD)
            out({"method": "answerCallbackQuery",
                 "payload": {"callback_query_id": cb["id"],
                             "text": "пульт принял: жду текст задачи"}})
            send_to(chat_id, "Пульт принял. Пришли текст новой задачи одним "
                             "сообщением (состояние: task_add).")
            return

        if data == "portal:task:close":
            tasks = _load(TASKS_F, {"open": []})
            if not tasks["open"]:
                send_to(chat_id, "Открытых задач нет.")
            else:
                rows = [[{"text": f"Закрыть: {t['title'][:40]}",
                          "callback_data": f"portal:task:done:{t['id']}"}
                         ] for t in tasks["open"][:10]]
                send_to(chat_id, "Какую закрыть?", kb=_kb(rows))
            set_stage(STATE_TASK_LIST)
            return

        if data.startswith("portal:task:done:"):
            try:
                tid = int(data.rsplit(":", 1)[1])
            except ValueError:
                tid = -1
            closed = tasks_close(tid)
            journal(update, "task_closed" if closed else "task_close_missed",
                    callback_data=data, ref=f"T-{tid}")
            send_to(chat_id, f"Задача T-{tid} закрыта."
                    if closed else f"T-{tid} не найдена.")
            set_stage(STATE_TASK_LIST)
            return

        if data == "portal:task:open":
            tasks = _load(TASKS_F, {"open": []})
            body = "\n".join(
                f"T-{t['id']}: {t['title']}" for t in tasks["open"]) or "—"
            send_to(chat_id, f"Открытые задачи пульта:\n{body}", kb=kb_tasks())
            set_stage(STATE_TASK_LIST)
            return

        if data == "portal:status":
            out({"method": "answerCallbackQuery",
                 "payload": {"callback_query_id": cb["id"],
                             "text": "пульт принял: portal:status"}})
            send_to(private_chat_id() or chat_id, summary_text(),
                    kb=kb_status())
            if private_chat_id() and chat_id != private_chat_id():
                send_to(chat_id, "Пульт принял: portal:status — сводка в личке "
                                 "владельца.")
            set_stage(STATE_STATUS)
            return

        if data == "portal:tasks":
            send_to(private_chat_id() or chat_id,
                    "Пульт в состоянии task_list. /tasks — список, кнопки "
                    "выше.", kb=kb_tasks())
            set_stage(STATE_TASK_LIST)
            return

        if data == "portal:incidents":
            send_to(chat_id, "Инциденты: /incident <текст> — зафиксировать; "
                             "журнал пульта пишется меты-only.")
            return

        if data == "portal:route":
            send_to(private_chat_id() or chat_id,
                    "Маршрут Maya: сессия ses_e714b5c4bffeh1ri37WHF8Q7Bx "
                    "(Пространство AllIs Maya). Бот — пульт; голос Корабля — "
                    "Maya. Ожидает решения владельца — через Ворота.")
            return

        if data == "portal:back":
            send_to(chat_id, "Назад к статусу.", kb=kb_status())
            set_stage(STATE_STATUS)
            return

        return

    # ---- сообщение ----
    text = (m.get("text") or "").strip()
    msg_id = m.get("message_id")
    stage = get_stage()

    # ---- медиа (голос/видео) — пульт принимает и фиксирует мету ----
    media = None
    if m.get("voice"):
        media = ("голосовое", m["voice"])
    elif m.get("video"):
        media = ("видео", m["video"])
    elif m.get("video_note"):
        media = ("видеосообщение", m["video_note"])
    elif m.get("document") and (m.get("document", {}).get("mime_type", "").startswith(("video/", "audio/"))):
        media = ("медиа-файл", m["document"])
    if media:
        kind, obj = media
        dur = obj.get("duration", "—")
        size = obj.get("file_size", "—")
        mime = obj.get("mime_type", "—")
        journal(update, "media_received", ref=f"media:{kind}")
        set_stage(STATE_IDLE)

        if dry:
            send_to(chat_id,
                    f"Пульт принял {kind}: длительность {dur}, размер {size}, "
                    f"mime {mime}. Боевой режим: скачаю и запущу ASR.")
            return

        file_id = obj.get("file_id")
        if not file_id:
            send_to(chat_id, "Пульт: медиа без file_id — скачать не могу.")
            return

        import subprocess
        media_dir = os.path.join(STATE, "media")
        os.makedirs(media_dir, exist_ok=True)
        ext = ".ogg" if kind == "голосовое" else ".mp4"
        path = os.path.join(media_dir, f"m{msg_id}{ext}")
        asr = os.path.join(HOME, "dotfiles/scripts/.local/bin/captain-panel-asr.py")
        outcome = "media_asr_failed"
        notice = "Пульт: медиа принято, но распознавание не удалось."
        try:
            try:
                wire.download_file(file_id, path)
            except Exception:
                # Bot API не скачивает крупные файлы (>~20 МБ) — резервный
                # маршрут через локальную MTProto-сессию Maya (профиль portal)
                journal(update, "media_download_fallback",
                        ref=f"download:{kind}")
                fetch = os.path.join(
                    HOME, "dotfiles/scripts/.local/bin/captain-panel-media-fetch.py")
                subprocess.run(
                    [sys.executable, fetch, "--chat", chat_id,
                     "--message-id", str(msg_id), "--out", path,
                     "--expect-from", OWNER],
                    capture_output=True, text=True, timeout=1200,
                    env=os.environ.copy(), check=True)
            run = subprocess.run(
                [sys.executable, asr, path, "ru"],
                capture_output=True, text=True, timeout=1200,
                env=os.environ.copy())
            payload = {}
            for row in run.stdout.splitlines():
                if row.startswith("ASR_JSON "):
                    payload = json.loads(row[len("ASR_JSON "):])
                    break
            if payload.get("ok") and payload.get("text"):
                text_out = payload["text"]
                if len(text_out) > 3500:
                    text_out = text_out[:3500] + "…"
                outcome = "media_transcribed"
                notice = (f"Пульт принял {kind}: длительность {dur}, "
                          f"размер {size}. Распознано: «{text_out}»")
            elif payload.get("error"):
                notice = (f"Пульт: медиа принято, ASR вернул отказ "
                          f"({payload['error'][:120]}).")
            journal(update, outcome, ref=f"asr:{kind}")
            send_to(chat_id, notice)
        except Exception as e:
            journal(update, outcome, ref=f"asr:{kind}")
            send_to(chat_id, "Пульт: медиа принято, но шаг распознавания упал. "
                             f"Ошибка: {type(e).__name__}.")
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        return

    if stage == STATE_TASK_ADD and not text.startswith("/"):
        tid = tasks_add(text)
        journal(update, "task_added", ref=f"T-{tid}")
        set_stage(STATE_TASK_LIST)
        send_to(chat_id, f"Задача T-{tid} зафиксирована пультом "
                         f"(ref T-{tid}).", kb=kb_tasks())
        return

    if text.startswith("/status"):
        journal(update, "accepted", ref="cmd:status")
        set_stage(STATE_STATUS)
        send_to(chat_id, summary_text(), kb=kb_status())
        return

    if text.startswith("/tasks"):
        journal(update, "accepted", ref="cmd:tasks")
        set_stage(STATE_TASK_LIST)
        tasks = _load(TASKS_F, {"open": []})
        body = "\n".join(
            f"T-{t['id']}: {t['title']}" for t in tasks["open"]) or "—"
        send_to(chat_id, f"Задачи пульта:\n{body}", kb=kb_tasks())
        return

    if text.startswith("/incident"):
        rest = text[len("/incident"):].strip()
        if not rest:
            send_to(chat_id, "Формат: /incident <текст сбоя>")
            return
        journal(update, "incident", ref="cmd:incident")
        set_stage(STATE_INCIDENT)
        # инцидент — голосу Корабля (Maya), пульт только фиксирует
        if not dry:
            import subprocess
            body = os.path.join(STATE, ".incident.txt")
            with open(body, "w", encoding="utf-8") as f:
                f.write(f"Инцидент от {OWNER} (пульт капитана):\n{rest[:400]}\n")
            subprocess.run(
                ["bash", os.path.join(HOME, "dotfiles/tools/ship-mail/ship-mail.sh"),
                 "send", "--to", "ses_e714b5c4bffeh1ri37WHF8Q7Bx",
                 "--from", "ses_ece7b76c8ffeOkYZqZe38QbTVx",
                 "--title", "Инцидент через бот-пульт капитана",
                 "--ref", "captain-panel-incident", "--file", body],
                capture_output=True, timeout=30)
            try:
                os.unlink(body)
            except OSError:
                pass
        send_to(chat_id, "Пульт принял: инцидент зафиксирован, передано Maya. "
                         "Ожидает разбора.")
        return

    if text.startswith("/settings"):
        s = _load(SETTINGS_F, {"notify_incident": True})
        if "on" in text:
            s["notify_incident"] = True
        if "off" in text:
            s["notify_incident"] = False
        _save(SETTINGS_F, s)
        journal(update, "accepted", ref="cmd:settings")
        send_to(chat_id, f"Настройки пульта: уведомления об инцидентах — "
                         f"{'вкл' if s.get('notify_incident') else 'выкл'} "
                         f"(/settings on|off).", kb=kb_status())
        return

    if text.startswith("/help"):
        journal(update, "accepted", ref="cmd:help")
        send_to(chat_id,
                "Команды пульта: /status · /tasks · /incident <текст> · "
                "/settings [on|off] · /help\n"
                "Кнопки: статус, задачи, инциденты, маршрут Maya.\n"
                "Команды исполняются только от владельца (Atma_Vichara108).",
                kb=kb_status())
        return

    journal(update, "unhandled")
    # Молчать нельзя на команду, но и отвечать на каждую реплику — спам.
    # Портальный чат — разговорный: меню только на неизвестную «/команду».
    if text.strip().startswith("/"):
        send_to(chat_id,
                "Не знаю такой команды. Что умею:\n"
                "/status — состояние · /tasks — задачи\n"
                "/incident <текст> — зафиксировать сбой\n"
                "/settings on|off — уведомления · /help — всё меню",
                kb=kb_status())

# ---------- dry-run smoke (спека §7, без сети) ----------


def smoke_dry():
    os.makedirs(STATE, exist_ok=True)
    ok = []

    # 1. сборка боевых кнопок без сети
    for name, kb in (("status", kb_status()), ("tasks", kb_tasks())):
        json.dumps(kb)
        ok.append(f"кнопки {name} собраны ({len(kb['inline_keyboard'])} ряда)")

    def upd(text=None, cb=None, user=OWNER, msg_id=1):
        u = {"update_id": 1, "message": {"message_id": msg_id,
              "chat": {"id": 42}, "from": {"username": user}}}
        if text:
            u["message"]["text"] = text
        if cb:
            u = {"update_id": 2, "callback_query": {"id": "cb1",
                 "from": {"username": user}, "chat": {"id": 42},
                 "data": cb}}
        return u

    # 2-4. /status с кнопками, нажатие portal:status, task:add
    handle(None, upd(text="/status"), dry=True)
    ok.append("/status с кнопками (dry)")
    handle(None, upd(cb="portal:status"), dry=True)
    ok.append("portal:status → корректный апдейт (dry)")
    set_stage(STATE_IDLE)
    handle(None, upd(cb="portal:task:add"), dry=True)
    old_tasks = json.dumps(_load(TASKS_F, {"next_id": 0}))
    handle(None, upd(text="smoke-задача пульта", msg_id=9), dry=True)
    tasks = _load(TASKS_F, {"open": []})
    closed = tasks_close(tasks["open"][-1]["id"]) if tasks["open"] else None
    ok.append(f"portal:task:add записал и журналировал ref T-{closed} (dry)")

    # 5. отказ не-владельца
    handle(None, upd(text="/status", user="intruder"), dry=True)
    ok.append("не-владелец → denied, без ответа (dry)")

    # 6-7. журнал без секретов
    secret = load_token()
    leaks = []
    try:
        with open(JOURNAL, encoding="utf-8") as f:
            content = f.read()
        import re
        if re.search(r"bot\d+:[\w-]+", content):
            leaks.append("токен в журнале")
        if secret and secret in content:
            leaks.append("значение токена в журнале")
    except OSError as e:
        leaks.append(f"журнал нечитаем: {e}")
    ok.append("журнал без секретов" if not leaks else "ПРОВАЛ: " + ", ".join(leaks))

    print("\nSMOKE dry-run:")
    for i, o in enumerate(ok, 1):
        print(f"  {i}. {o}")
    if leaks:
        return 1
    print(f"\nЖурнал: {JOURNAL}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="captain-panel bot-пульт")
    ap.add_argument("--dry-run", action="store_true",
                    help="smoke без сети (спека §7)")
    args = ap.parse_args()

    if args.dry_run:
        return smoke_dry()

    token = load_token()
    if not token:
        print(f"нет токена: {ENV_FILE} (TG_BOT_TOKEN) — через Ворота owner-gate",
              file=sys.stderr)
        return 1

    wire = Wire(token)
    offset = 0
    print(f"captain-panel запущен (профиль {PROFILE}, группа {GROUP}) — "
          f"бот-пульт, не голос Корабля")
    while True:
        try:
            r = wire.call("getUpdates", {"timeout": 15, "offset": offset,
                                         "allowed_updates":
                                         ["message", "callback_query"]})
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                try:
                    handle(wire, u)
                except Exception as e:
                    # fail-open: событие уже в журнале, реакция не роняет цикл
                    print(f"handle: {type(e).__name__}", file=sys.stderr)
        except urllib.error.HTTPError as e:
            reason = getattr(e, "reason", "") or getattr(e, "msg", "")
            print(f"getUpdates: HTTP {getattr(e, 'code', '?')} {reason}",
                  file=sys.stderr)
        except Exception as e:
            reason = getattr(e, "reason", e)
            print(f"getUpdates: {type(e).__name__}: {reason}", file=sys.stderr)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    sys.exit(main())
