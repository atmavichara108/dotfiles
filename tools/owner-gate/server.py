#!/usr/bin/env python3
"""
owner-gate — MCP-сервер «Ворота владельца» (ИЦ dotfiles, 2026-10-23).

Назначение: владелец отвечает на вопросы ИЦ/агентов ФОРМАМИ В ЭТОМ ЖЕ ВЫЗОВЕ
(OpenCode 2.1.4, MCP elicitation), без разрыва сессии и без «жду твоего решения»
в чате. Форма показывается только при вызове инструмента — сервер спит на stdio
и просыпается по событию (tools/call).

Принципы (канон):
- спящий по умолчанию: без tools/call сервер ничего не делает и не шумит;
- строго по событиям: каждый вызов несёт event из events.json; неизвестное
  событие = отказ без формы (формы не самозарождаются);
- содержание форм и ответов НИКОГДА не пишется в журнал и не попадает в репо
  (секреты — только через ask_secret, ответ уходит агенту, в журнал — метаданные);
- отказ/отмена — честный результат, агенту возвращается «declined/cancelled»;
  молчаливого «поддакивания» нет (S0-А1);
- канон: слово Rudra 2026-10-23 («создавай релевантные и используемые, пускай
  спят и включаются только по событиям»).

Транспорт: MCP over stdio, newline-delimited JSON-RPC 2.0. Зависимостей нет
(только стандартная библиотека Python 3).
"""

import json
import os
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
EVENTS_FILE = os.path.join(HERE, "events.json")
JOURNAL_DIR = os.path.expanduser("~/.local/state/opencode/owner-gate")
JOURNAL_FILE = os.path.join(JOURNAL_DIR, "journal.jsonl")

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "owner-gate", "version": "0.1.0"}
SERVER_TITLE = "Ворота владельца — формы решения по событиям"


# ---------------------------------------------------------------- события
def load_events():
    """Заявленные события форм. Пусто/битый файл = ворота заперты (без формы)."""
    try:
        with open(EVENTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {e["id"]: e for e in data.get("events", [])}
    except Exception:
        return {}


def journal(record):
    """Метаданные-only журнал ворот (никогда — содержание ответов)."""
    try:
        os.makedirs(JOURNAL_DIR, exist_ok=True)
        rec = {"ts": int(time.time()), **record}
        with open(JOURNAL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass  # журнал — вспомогательный след, не критичный путь


# ---------------------------------------------------------------- транспорт
def send(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def read_message():
    line = sys.stdin.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return read_message()
    return json.loads(line)


def result(msg_id, result_obj):
    send({"jsonrpc": "2.0", "id": msg_id, "result": result_obj})


def error(msg_id, code, message):
    send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})


# ---------------------------------------------------------------- elicitation
def elicit(msg_id, message, schema, meta=None):
    """
    Показать форму владельцу (MCP elicitation/create) и дождаться ответа.
    Возвращает dict: {"action": "accept", "content": {...}} либо
    {"action": "decline"/"cancel"} либо {"action":"error",...} при обрыве.
    """
    params = {"message": message, "requestedSchema": schema}
    if meta:
        params["_meta"] = meta  # опционально: контекст для клиента
    send({"jsonrpc": "2.0", "id": msg_id, "method": "elicitation/create", "params": params})
    # Ждём ответ клиента именно на этот id (уведомления в стороне — не наше).
    while True:
        msg = read_message()
        if msg is None:
            return {"action": "error", "reason": "client-closed"}
        mid = msg.get("id")
        if mid == msg_id and ("result" in msg or "error" in msg):
            if "result" in msg:
                res = msg.get("result") or {}
                action = res.get("action", "cancel")
                if action == "accept":
                    return {"action": "accept", "content": res.get("content") or {}}
                return {"action": action}
            return {"action": "error", "reason": msg.get("error", {}).get("message", "?")}
        # постороннее сообщение во время формы — игнорируем (клиент ждёт наш Tool-результат)


# ---------------------------------------------------------------- инструменты
def tool_schema(props, required=None):
    return {
        "type": "object",
        "properties": props,
        "required": required or ["event"],
        "additionalProperties": False,
    }


TOOLS = [
    {
        "name": "ask_confirm",
        "title": "Ворота: да/нет",
        "description": (
            "Форма да/нет владельцу. Вызывать ТОЛЬКО на заявленном событии "
            "(event из events.json), когда нужно апрув/запрет: опасный apply, "
            "обход гейта, отправка письма вне очереди. Ответ accept=true — "
            "одобрено, accept=false — не одобрено, decline/cancel — владелец "
            "не ответил (НЕ считать согласием)."
        ),
        "inputSchema": tool_schema(
            {
                "event": {"type": "string", "description": "id события из events.json"},
                "question": {"type": "string", "description": "Вопрос простыми словами"},
                "yes_label": {"type": "string", "description": "Подпись кнопки «да» (по умолч. Да)"},
                "no_label": {"type": "string", "description": "Подпись кнопки «нет» (по умолч. Нет)"},
            },
            ["event", "question"],
        ),
    },
    {
        "name": "ask_choice",
        "title": "Ворота: выбор варианта",
        "description": (
            "Форма выбора одного варианта из списка. Для канонических развилок "
            "(вариант-1/вариант-2, Bases/Dataview, маршрут ведомства). Список "
            "вариантов — 2..6 пунктов, каждый с выгодой/риском одной строкой."
        ),
        "inputSchema": tool_schema(
            {
                "event": {"type": "string", "description": "id события из events.json"},
                "question": {"type": "string", "description": "Что выбираем, простыми словами"},
                "options": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "string"},
                            "label": {"type": "string"},
                            "hint": {"type": "string", "description": "выгода/риск одной строкой"},
                        },
                        "required": ["value", "label"],
                        "additionalProperties": False,
                    },
                    "minItems": 2,
                    "maxItems": 6,
                },
            },
            ["event", "question", "options"],
        ),
    },
    {
        "name": "ask_secret",
        "title": "Ворота: секрет владельца",
        "description": (
            "Форма для значения-секрета (ключ/пароль/токен), которое должен "
            "вставить только владелец. Ответ уходит агенту этим же вызовом: "
            "агент кладёт его в файл 600 вне репо. В журнал и в репо значение "
            "НЕ попадает никогда."
        ),
        "inputSchema": tool_schema(
            {
                "event": {"type": "string", "description": "id события из events.json"},
                "what": {"type": "string", "description": "Какой секрет и зачем (без самого секрета)"},
                "hint": {"type": "string", "description": "Где взять (панель/URL), если известно"},
                "target": {"type": "string", "description": "Имя файла внутри ~/.secrets/ (без путей): сервер сам запишет значение (600), минуя слой редактирования результатов. Без target значение вернётся агенту (может быть отредактировано слоем)."},
            },
            ["event", "what"],
        ),
    },
    {
        "name": "ask_dns",
        "title": "Ворота: DNS-запись",
        "description": (
            "Форма для DNS-записей, которые вставляет только владелец "
            "(Namecheap/регистратор). Поля: host, тип, значение. Ответ уходит "
            "агенту этим же вызовом; проверка встаёт на агента (dig)."
        ),
        "inputSchema": tool_schema(
            {
                "event": {"type": "string", "description": "id события из events.json"},
                "host": {"type": "string", "description": "Имя записи (напр. resend._domainkey.re-search.wiki)"},
                "rtype": {
                    "type": "string",
                    "enum": ["MX", "TXT", "CNAME", "A", "SPF", "DKIM"],
                    "description": "Тип записи",
                },
                "value_hint": {"type": "string", "description": "Ожидаемое значение/подсказка (необязательно)"},
            },
            ["event", "host", "rtype"],
        ),
    },
]


def tool_result(payload):
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


def check_event(event_id):
    events = load_events()
    ev = events.get(event_id)
    if not ev:
        journal({"tool_scope": "unknown-event", "event": str(event_id)[:64]})
        return None
    return ev


def tool_call(msg_id, name, args):
    events = load_events()
    event_id = (args or {}).get("event", "")
    ev = check_event(event_id)
    if ev is None:
        result(
            msg_id,
            tool_result(
                {
                    "ok": False,
                    "action": "refused",
                    "reason": "unknown-event",
                    "message": (
                        f"Событие «{event_id}» не заявлено в events.json — форма не показана. "
                        "Заяви событие (что случится и при каком триггере) и повтори."
                    ),
                }
            ),
        )
        return

    meta = {
        "title": ev.get("title", ""),
        "event": event_id,
        "tool": name,
        "canon_ref": ev.get("canon_ref", ""),
    }

    if name == "ask_confirm":
        question = args.get("question", "")
        yes = args.get("yes_label", "Да")
        no = args.get("no_label", "Нет")
        ans = elicit(
            msg_id,
            f"❗ {question}\n\n[{event_id}] {ev.get('title','')}",
            {
                "type": "object",
                "properties": {
                    "confirm": {"type": "boolean", "title": f"«{yes}» = согласен, «{no}» = нет"},
                },
                "required": ["confirm"],
                "additionalProperties": False,
            },
            meta=meta,
        )
        if ans["action"] != "accept":
            journal({"tool": name, "event": event_id, "action": ans["action"]})
            result(msg_id, tool_result({"ok": False, "action": ans["action"],
                                        "message": "Владелец не ответил — НЕ считать согласием."}))
            return
        val = bool((ans.get("content") or {}).get("confirm"))
        journal({"tool": name, "event": event_id, "action": "accept", "value_bool": val})
        result(msg_id, tool_result({"ok": True, "action": "accept", "confirm": val,
                                    "message": "Одобрено." if val else "Не одобрено."}))
        return

    if name == "ask_choice":
        options = args.get("options") or []
        if len(options) < 2:
            result(msg_id, tool_result({"ok": False, "action": "refused",
                                        "reason": "need-2-6-options"}))
            return
        enum = [str(o["value"]) for o in options]
        labels = {str(o["value"]): o.get("hint") or o.get("label", "") for o in options}
        ans = elicit(
            msg_id,
            f"❗ {args.get('question','')}\n\n[{event_id}] {ev.get('title','')}",
            {
                "type": "object",
                "properties": {
                    "choice": {
                        "type": "string",
                        "title": "Вариант",
                        "enum": enum,
                        "oneOf": [{"const": v, "title": labels[v]} for v in enum],
                    }
                },
                "required": ["choice"],
                "additionalProperties": False,
            },
            meta=meta,
        )
        if ans["action"] != "accept":
            journal({"tool": name, "event": event_id, "action": ans["action"]})
            result(msg_id, tool_result({"ok": False, "action": ans["action"],
                                        "message": "Владелец не выбрал."}))
            return
        val = str((ans.get("content") or {}).get("choice", ""))
        journal({"tool": name, "event": event_id, "action": "accept", "choice": val})
        result(msg_id, tool_result({"ok": True, "action": "accept", "choice": val}))
        return

    if name == "ask_secret":
        what = args.get("what", "")
        hint = args.get("hint", "")
        target = (args.get("target") or "").strip()
        if target and (("/" in target) or ("\\" in target)
                       or target.startswith(".") or ".." in target):
            result(msg_id, tool_result({
                "ok": False, "action": "refused", "reason": "bad-target",
                "message": "target — только имя файла внутри ~/.secrets/ "
                           "(без путей), иначе отказ.",
            }))
            return
        ans = elicit(
            msg_id,
            f"❗ Вставь секрет: {what}\n\n[{event_id}] {ev.get('title','')}"
            + (f"\nПодсказка: {hint}" if hint else "")
            + ("\nЗначение будет записано файлом ~/.secrets/"
               + target + " (600); в журнал/репо/вывод не попадёт."
               if target else
               "\nЗначение уйдёт агенту этим же вызовом; в журнал/репо не "
               "попадёт. ВНИМАНИЕ: слой исполнения может редактировать "
               "секретоподобные строки в результате — для надёжности "
               "передавай target."),
            {
                "type": "object",
                "properties": {
                    "secret": {"type": "string", "title": what or "Секрет"},
                },
                "required": ["secret"],
                "additionalProperties": False,
            },
            meta=meta,
        )
        if ans["action"] != "accept":
            journal({"tool": name, "event": event_id, "action": ans["action"]})
            result(msg_id, tool_result({"ok": False, "action": ans["action"],
                                        "message": "Секрет не получен."}))
            return
        val = str((ans.get("content") or {}).get("secret", ""))
        if target:
            # Серверная запись: значение не покидает процесс Ворот — мимо
            # слоя редактирования результатов (инцидент apinex/Мастерская).
            path = os.path.expanduser("~/.secrets/" + target)
            try:
                os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                             0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(val)
            except Exception as e:  # noqa: BLE001
                journal({"tool": name, "event": event_id,
                         "action": "accept", "secret_len": len(val),
                         "target": target, "write": "failed"})
                result(msg_id, tool_result({
                    "ok": False, "action": "accept", "target": target,
                    "message": f"запись не удалась: {type(e).__name__} "
                               f"(значение не сохранено)",
                }))
                return
            journal({"tool": name, "event": event_id, "action": "accept",
                     "secret_len": len(val), "target": target,
                     "write": "ok"})
            result(msg_id, tool_result({
                "ok": True, "action": "accept", "target": target,
                "secret_len": len(val),
                "message": f"записано {path} (600, серверная запись)",
            }))
            return
        journal({"tool": name, "event": event_id, "action": "accept",
                 "secret_len": len(val)})  # длиной, не значением
        result(msg_id, tool_result({"ok": True, "action": "accept", "secret": val}))
        return

    if name == "ask_dns":
        host = args.get("host", "")
        rtype = args.get("rtype", "")
        hint = args.get("value_hint", "")
        ans = elicit(
            msg_id,
            f"❗ Вставь DNS-запись в панель регистратора.\n\n[{event_id}] {ev.get('title','')}\n"
            f"Host: {host}\nТип: {rtype}"
            + (f"\nОжидаемое/подсказка: {hint}" if hint else ""),
            {
                "type": "object",
                "properties": {
                    "value": {"type": "string", "title": f"Значение записи {rtype} для {host}"},
                    "done": {"type": "boolean", "title": "Запись вставлена в панели"},
                },
                "required": ["value", "done"],
                "additionalProperties": False,
            },
            meta=meta,
        )
        if ans["action"] != "accept":
            journal({"tool": name, "event": event_id, "action": ans["action"]})
            result(msg_id, tool_result({"ok": False, "action": ans["action"],
                                        "message": "Запись не получена."}))
            return
        content = ans.get("content") or {}
        journal({"tool": name, "event": event_id, "action": "accept",
                 "dns_host": host, "dns_type": rtype, "dns_done": bool(content.get("done"))})
        result(msg_id, tool_result({
            "ok": True, "action": "accept",
            "record": {"host": host, "type": rtype,
                       "value": str(content.get("value", "")),
                       "inserted": bool(content.get("done"))},
        }))
        return

    error(msg_id, -32602, f"unknown tool: {name}")


# ---------------------------------------------------------------- основной цикл
def handle(msg):
    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        result(msg_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}, "elicitation": {}},
            "serverInfo": {**SERVER_INFO, "title": SERVER_TITLE},
        })
        return

    if method in ("notifications/initialized", "notifications/cancelled"):
        return

    if method == "ping":
        result(msg_id, {})
        return

    if method == "tools/list":
        result(msg_id, {
            "tools": [
                {"name": t["name"], "title": t["title"], "description": t["description"],
                 "inputSchema": t["inputSchema"]}
                for t in TOOLS
            ]
        })
        return

    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name", "")
        args = params.get("arguments") or {}
        if name not in {t["name"] for t in TOOLS}:
            error(msg_id, -32602, f"unknown tool: {name}")
            return
        trace = str(uuid.uuid4())[:8]
        journal({"tool": name, "event": str(args.get("event", ""))[:64], "phase": "call", "trace": trace})
        tool_call(msg_id, name, args)
        return

    if msg_id is not None:
        error(msg_id, -32601, f"method not found: {method}")


def main():
    # Ворота спят, пока не пришёл tools/call. Инициализация — только рукопожатие.
    while True:
        try:
            msg = read_message()
        except Exception:
            continue
        if msg is None:
            break
        handle(msg)


if __name__ == "__main__":
    main()
