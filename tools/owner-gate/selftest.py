#!/usr/bin/env python3
"""
selftest — проверка Ворот владельца без OpenCode (stdio-петля наизнанку).

Сценарии:
  1. initialize → protocolVersion/capabilities/elicitation
  2. tools/list → 4 инструмента с событийной проверкой
  3. tools/call ask_confirm (событие ship.override) → elicitation/create →
     клиент отвечает accept → результат ok/confirm
  4. tools/call ask_choice (canon.choice) → accept → choice
  5. tools/call ask_secret (mail-hub.secret) → accept → secret; в журнале — длина, не значение
  6. неизвестное событие → refused без формы
  7. decline честно возвращается (не молчание)
  8. ping
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "server.py")
OK, FAIL = 0, 0


def check(label, cond, extra=""):
    global OK, FAIL
    mark = "✅" if cond else "❌"
    if cond:
        OK += 1
    else:
        FAIL += 1
    print(f"{mark} {label}" + (f" — {extra}" if extra else ""))


class Client:
    def __init__(self):
        self.proc = subprocess.Popen(
            [sys.executable, SERVER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, cwd=HERE,
        )
        self.n = 0

    def send(self, obj):
        self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def recv(self):
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("сервер закрыл stdout")
        return json.loads(line)

    def call(self, method, params=None, notification=False):
        self.n += 1
        mid = None if notification else self.n
        obj = {"jsonrpc": "2.0", "method": method}
        if mid is not None:
            obj["id"] = mid
        if params is not None:
            obj["params"] = params
        self.send(obj)
        return mid if not notification else None

    def stop(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def main():
    c = Client()
    try:
        # 1. initialize
        c.call("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "owner-gate-selftest", "version": "0.1.0"},
        })
        r = c.recv()
        check("initialize", r.get("result", {}).get("capabilities", {}).get("elicitation") == {}
              and r["result"]["serverInfo"]["name"] == "owner-gate",
              r.get("result", {}).get("protocolVersion"))
        c.call("notifications/initialized", notification=True)

        # 2. tools/list
        c.call("tools/list")
        r = c.recv()
        tools = {t["name"] for t in r.get("result", {}).get("tools", [])}
        check("tools/list", {"ask_confirm", "ask_choice", "ask_secret", "ask_dns"} <= tools, str(sorted(tools)))

        # 3. ask_confirm → elicitation → accept
        c.call("tools/call", {"name": "ask_confirm", "arguments": {
            "event": "ship.override",
            "question": "Тест: обойти гейт?",
        }})
        req = c.recv()
        check("elicitation/create пришёл", req.get("method") == "elicitation/create",
              json.dumps(req.get("params", {}).get("requestedSchema", {}), ensure_ascii=False))
        c.send({"jsonrpc": "2.0", "id": req["id"],
                "result": {"action": "accept", "content": {"confirm": True}}})
        r = c.recv()
        payload = json.loads(r["result"]["content"][0]["text"])
        check("confirm accept→true", payload.get("ok") and payload.get("confirm") is True, payload.get("message"))

        # 4. ask_choice
        c.call("tools/call", {"name": "ask_choice", "arguments": {
            "event": "canon.choice",
            "question": "Выбор:",
            "options": [{"value": "v1", "label": "Вариант-1", "hint": "запас токенов"},
                        {"value": "v2", "label": "Вариант-2", "hint": "глагольная сила"}],
        }})
        req = c.recv()
        check("choice: форма пришла", req.get("method") == "elicitation/create")
        c.send({"jsonrpc": "2.0", "id": req["id"],
                "result": {"action": "accept", "content": {"choice": "v1"}}})
        r = c.recv()
        payload = json.loads(r["result"]["content"][0]["text"])
        check("choice accept→v1", payload.get("choice") == "v1")

        # 5. ask_secret
        c.call("tools/call", {"name": "ask_secret", "arguments": {
            "event": "mail-hub.secret", "what": "Ключ Resend (тест)",
        }})
        req = c.recv()
        c.send({"jsonrpc": "2.0", "id": req["id"],
                "result": {"action": "accept", "content": {"secret": "re_TESTVALUE12345"}}})
        r = c.recv()
        payload = json.loads(r["result"]["content"][0]["text"])
        check("secret accept→значение ушло агенту", payload.get("secret") == "re_TESTVALUE12345")

        # 6. неизвестное событие — отказ без формы
        c.call("tools/call", {"name": "ask_confirm", "arguments": {
            "event": "нет-такого-события", "question": "провокация",
        }})
        r = c.recv()
        payload = json.loads(r["result"]["content"][0]["text"])
        check("неизвестное событие → refused без формы",
              payload.get("action") == "refused" and "не заявлено" in payload.get("message", ""))

        # 7. decline честен
        c.call("tools/call", {"name": "ask_confirm", "arguments": {
            "event": "apply.approve", "question": "Тест отказа",
        }})
        req = c.recv()
        c.send({"jsonrpc": "2.0", "id": req["id"], "result": {"action": "decline"}})
        r = c.recv()
        payload = json.loads(r["result"]["content"][0]["text"])
        check("decline честно вернулся (не согласие)",
              payload.get("action") == "declined" or payload.get("action") == "decline",
              payload.get("message"))

        # 8. ping
        c.call("ping")
        r = c.recv()
        check("ping", r.get("result") == {})

        # 9. журнал: только метаданные
        jf = os.path.expanduser("~/.local/state/opencode/owner-gate/journal.jsonl")
        leak = ""
        if os.path.exists(jf):
            blob = open(jf, encoding="utf-8").read()
            leak = "re_TESTVALUE12345" if "re_TESTVALUE12345" in blob else ""
        check("журнал без секретов", not leak)
    finally:
        c.stop()

    print(f"\nИТОГ: {OK} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
