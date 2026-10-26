#!/usr/bin/env python3
"""wake — зов сессии с предпроверкой (Р-031).

Зов = POST /api/session/<id>/prompt с текстом о письме. Без слепых
повторов: перед зовом предпроверка —
  1. сессия жива (GET /api/session/<id> — 200);
  2. агент резолвится в проекте сессии (.opencode/agent/<agent>.md);
  3. нет активного хода (time.updated не свежее time.idle — «не занят»);
  4. rate-limit: один зов на SID за 900 секунд (state на диске).
Не прошёл предпроверку → отказ + инцидент в журнал (НЕ слепой повтор).
Журнал меты-only: ~/.local/state/opencode/wake/journal.jsonl
(ts, sid, ok/skip-refuse, причина, длина текста — без тела и секретов).

Использование:
  python3 wake.py <sessionID> --text "..."   # зов с явным текстом
  python3 wake.py <sessionID> --file PATH    # текст из файла
  python3 wake.py --status                   # rate-limit состояние

Коды: 0 отправлен · 1 отказ (предпроверка/лимит) · 2 usage/API.
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

ENDPOINT = os.environ.get("OPENCODE_ENDPOINT", "http://127.0.0.1:49374")
SERVICE_JSON = os.path.expanduser("~/.config/opencode/service.json")
WAKE_DIR = os.path.expanduser("~/.local/state/opencode/wake")
JOURNAL = os.path.join(WAKE_DIR, "journal.jsonl")
RATELIMIT = int(os.environ.get("WAKE_RATELIMIT_SEC", "900"))


def die(msg, code=2):
    print(f"wake: {msg}", file=sys.stderr)
    sys.exit(code)


def journal(row):
    os.makedirs(WAKE_DIR, exist_ok=True)
    with open(JOURNAL, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def headers():
    try:
        tok = json.load(open(SERVICE_JSON, encoding="utf-8")).get("password", "")
    except Exception:  # noqa: BLE001
        die("нет service.json — токен недоступен")
    return {"Authorization":
            "Basic " + base64.b64encode(f"opencode:{tok}".encode()).decode(),
            "Content-Type": "application/json"}


def projects_index():
    req = urllib.request.Request(ENDPOINT + "/api/project", headers=headers())
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode())
    d = d.get("data", d) if isinstance(d, dict) else d
    return {p.get("id"): p.get("canonical") for p in d if isinstance(p, dict)}


def preflight(sid):
    """-> (ok: bool, reason: str, session_data)"""
    req = urllib.request.Request(f"{ENDPOINT}/api/session/{sid}",
                                 headers=headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return False, f"session not alive (HTTP {e.code})", None
    except Exception as e:  # noqa: BLE001
        return False, f"api fail: {type(e).__name__}", None
    d = d.get("data", d) if isinstance(d, dict) else d
    agent = d.get("agent")
    pid = d.get("projectID", "")
    canonical = projects_index().get(pid)
    if agent and canonical:
        path = os.path.join(canonical, ".opencode/agent", f"{agent}.md")
        if not os.path.exists(path):
            return False, f"agent {agent} not resolvable in {canonical}", d
    t = d.get("time") or {}
    upd, idl = t.get("updated") or t.get("created") or 0, t.get("idle") or 0
    if upd and idl and upd > idl:
        return False, "session busy (active turn) — не зовём", d
    return True, "", d


def rate_limited(sid):
    state_file = os.path.join(WAKE_DIR, "ratelimit.json")
    try:
        state = json.load(open(state_file, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        state = {}
    last = state.get(sid, 0)
    if time.time() - last < RATELIMIT:
        return True, int(RATELIMIT - (time.time() - last))
    state[sid] = int(time.time())
    os.makedirs(WAKE_DIR, exist_ok=True)
    with open(state_file + ".tmp", "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(state_file + ".tmp", state_file)
    return False, 0


def main(argv):
    if "--status" in argv:
        state_file = os.path.join(WAKE_DIR, "ratelimit.json")
        try:
            state = json.load(open(state_file, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            state = {}
        now = time.time()
        for sid, ts in sorted(state.items()):
            left = int(RATELIMIT - (now - ts))
            print(f"{sid}: {'готов' if left <= 0 else f'пауза {left}с'}")
        return 0
    if "--sweep" in argv:
        # Слаженность без человека: у кого в ящике непрочитанные письма —
        # тех зовём (те же предпроверки и лимит), текст нейтральный.
        home = os.path.expanduser("~/.local/share/ship-mail/inbox")
        woken = 0
        if os.path.isdir(home):
            for sid in sorted(os.listdir(home)):
                box = os.path.join(home, sid)
                if not os.path.isdir(box):
                    continue
                n = len([f for f in os.listdir(box)
                         if f.endswith(".md") and os.path.isfile(
                             os.path.join(box, f))])
                if n == 0:
                    continue
                ok, reason, _ = preflight(sid)
                if not ok:
                    journal({"ts": int(time.time()), "sid": sid,
                             "result": "refused", "reason": reason,
                             "unread": n})
                    print(f"wake-sweep: {sid[:20]}… {n} писем, но ОТКАЗ: {reason}")
                    continue
                limited, left = rate_limited(sid)
                if limited:
                    print(f"wake-sweep: {sid[:20]}… {n} писем, лимит ({left}с)")
                    continue
                text = (f"ship-mail: у тебя {n} непрочитанных писем в ящике. "
                        f"Прочти первым шагом хода (ship-mail.sh inbox), "
                        f"обработай и ack.")
                rc = _send(sid, text)
                if rc == 0:
                    woken += 1
        print(f"wake-sweep: разбужено {woken}")
        return 0
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 1:
        die("usage: wake.py <sessionID> --text ... | --file ... | --status")
    sid = args[0]
    if not sid.startswith("ses_"):
        die("sessionID должен начинаться с ses_")
    text = ""
    if "--text" in argv:
        i = argv.index("--text")
        text = argv[i + 1] if i + 1 < len(argv) else ""
    elif "--file" in argv:
        i = argv.index("--file")
        text = open(argv[i + 1], encoding="utf-8").read()
    else:
        die("нужен --text или --file")
    if not text.strip():
        die("пустой текст — зов нечего")

    ok, reason, d = preflight(sid)
    if not ok:
        journal({"ts": int(time.time()), "sid": sid, "result": "refused",
                 "reason": reason, "text_len": len(text)})
        print(f"wake: ОТКАЗ (не слепой повтор): {reason}")
        return 1
    limited, left = rate_limited(sid)
    if limited:
        journal({"ts": int(time.time()), "sid": sid,
                 "result": "rate-limited", "wait": left, "text_len": len(text)})
        print(f"wake: лимит — один зов на SID за {RATELIMIT}с, осталось {left}с")
        return 1
    return _send(sid, text)


def _send(sid, text):
    req = urllib.request.Request(
        f"{ENDPOINT}/api/session/{sid}/prompt",
        data=json.dumps({"text": text}).encode(),
        headers=headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    except Exception as e:  # noqa: BLE001
        journal({"ts": int(time.time()), "sid": sid, "result": "failed",
                 "reason": f"{type(e).__name__}", "text_len": len(text)})
        print(f"wake: зов не ушёл ({type(e).__name__}) — осталось в журнале")
        return 1
    journal({"ts": int(time.time()), "sid": sid, "result": "ok",
             "text_len": len(text)})
    print(f"wake: OK — зов ушёл {sid} (длина {len(text)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
