#!/usr/bin/env python3
"""drift — три оси дрейфа канала (общий модуль для session-cop и watch-logs).

Мандат sign-rules-to-infra (ЦУ 2026-10-30): дрейф должен ловиться без
запуска копа — поэтому оси вынесены в переиспользуемый модуль.

Оси:
  1. channel: sent/queued без следа у получателя (read-gate sqlite);
  2. claims: активные claims вне peer-registry;
  3. inbox-names: имя файла inbox vs программно извлечённый frontmatter from.
"""
import json
import os
import re
import sqlite3
import time

MAIL_DIR = os.path.expanduser("~/.local/state/opencode/mail")
RECEIPTS = os.path.join(MAIL_DIR, "receipts-out.jsonl")
REGISTRY = os.path.expanduser(
    "~/Projects/OpenCode-Vault/04-Memory/peer-registry.md")
INBOX = os.path.expanduser("~/.local/share/ship-mail/inbox")
LEDGER = os.path.expanduser("~/.local/state/opencode/lineage/ledger.jsonl")
DB = os.path.expanduser("~/.local/share/opencode/opencode.db")


def registry_ids():
    ids = set()
    if os.path.exists(REGISTRY):
        for line in open(REGISTRY, encoding="utf-8"):
            for m in re.finditer(r"ses_[A-Za-z0-9]+", line):
                ids.add(m.group(0))
    return ids


def _delivered(to, mid):
    """След у получателя: строка с message-id в session_message (read-gate)."""
    if not os.path.exists(DB):
        return None  # неизвестно — не утверждаем
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        got = con.execute(
            "SELECT 1 FROM session_message WHERE session_id=? AND type='user' "
            "AND data LIKE ?", (to, f"%{mid[:16]}%")).fetchone()
        return bool(got)
    except Exception:  # noqa: BLE001
        return None


def axis_channel(limit=40):
    """Ось 1: sent/queued без delivered у получателя."""
    problems = []
    if not os.path.exists(RECEIPTS):
        return problems
    rows = []
    for line in open(RECEIPTS, encoding="utf-8"):
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    sent = [r for r in rows if r.get("event") in ("sent", "queued")]
    for r in sent[-limit:]:
        to, mid = r.get("to"), r.get("message_id", "")
        if not to or not mid:
            continue
        got = _delivered(to, mid)
        if got is False:
            problems.append({"axis": "channel",
                             "class": "sent-without-delivered",
                             "sid": to, "message_id": mid,
                             "event": r.get("event")})
    return problems


def axis_claims(alive_cache=None):
    """Ось 2: активные claims (ledger) вне peer-registry.

    Улучшение (вердикт ЦУ claims-verdict 2026-10-30): проверяем ЖИВОСТЬ
    сессии claim'а — claim на мёртвую сессию = устаревший (класс
    «claim после смерти сессии»), авто-кандидат на истечение; claim на
    живую нереестровую = «реестр догоняет». Живость — с кэшем в state
    (TTL 15м), чтобы не долбить API каждый прогон.
    """
    problems = []
    if not os.path.exists(LEDGER):
        return problems
    reg = registry_ids()
    # всё, что не похоже на ses_* — имена, не сессии (легаси-id стиля)
    for line in open(LEDGER, encoding="utf-8"):
        try:
            d = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if "claim" not in d.get("edge", ""):
            continue
        note = d.get("note", "")
        if "op=release" in note:
            continue  # снятый claim
        sid = d.get("session_id", "")
        if not sid or sid in reg:
            continue
        if not sid.startswith("ses_"):
            problems.append({"axis": "claims",
                             "class": "claim-legacy-name",
                             "sid": sid, "ref": d.get("ref", ""),
                             "note": note[:120]})
            continue
        alive = session_alive(sid, alive_cache)
        if alive is False:
            # 404: возможно усечённый id (фантомный префикс) — ищем живую
            # сессию с таким префиксом (INC-18 наоборот: claim указывает
            # неполным адресом).
            full = _find_by_prefix(sid)
            if full:
                problems.append({"axis": "claims",
                                 "class": "claim-truncated-id",
                                 "sid": sid, "ref": d.get("ref", ""),
                                 "note": note[:120],
                                 "full_sid": full,
                                 "treatment": "починка id в claim"})
            else:
                problems.append({"axis": "claims",
                                 "class": "claim-after-session-death",
                                 "sid": sid, "ref": d.get("ref", ""),
                                 "note": note[:120],
                                 "treatment": "истечение по TTL waits"})
        else:
            problems.append({"axis": "claims",
                             "class": "claim-outside-registry",
                             "sid": sid, "ref": d.get("ref", ""),
                             "note": note[:120]})
    return problems


def _find_by_prefix(prefix):
    """Живая сессия, чей id начинается с prefix (лечение усечённых id)."""
    if not prefix.startswith("ses_"):
        return None
    import base64
    import urllib.request
    try:
        tok = json.load(open(os.path.expanduser(
            "~/.config/opencode/service.json"),
            encoding="utf-8")).get("password", "")
    except Exception:  # noqa: BLE001
        return None
    if not tok:
        return None
    req = urllib.request.Request(
        "http://127.0.0.1:49374/api/session",
        headers={"Authorization": "Basic " + base64.b64encode(
            f"opencode:{tok}".encode()).decode()})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read().decode())
        rows = body.get("data", body) if isinstance(body, dict) else body
        for s in rows:
            if isinstance(s, dict) and str(s.get("id", "")).startswith(prefix):
                return s.get("id")
    except Exception:  # noqa: BLE001
        pass
    return None


ALIVE_TTL = 900  # 15 минут


def session_alive(sid, cache=None):
    """Жива ли сессия (кэш в state). True/False/None(неизвестно)."""
    if not sid.startswith("ses_"):
        return None
    cache_file = os.path.expanduser("~/.local/state/opencode/watch/"
                                    "session-alive.json")
    now = time.time()
    state = {}
    try:
        state = json.load(open(cache_file, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    if sid in state and now - state[sid].get("checked_ts", 0) < ALIVE_TTL:
        return state[sid].get("alive")
    import base64
    import urllib.error
    import urllib.request
    tok = ""
    try:
        tok = json.load(open(os.path.expanduser(
            "~/.config/opencode/service.json"),
            encoding="utf-8")).get("password", "")
    except Exception:  # noqa: BLE001
        pass
    if not tok:
        return None
    req = urllib.request.Request(
        f"http://127.0.0.1:49374/api/session/{sid}",
        headers={"Authorization": "Basic " + base64.b64encode(
            f"opencode:{tok}".encode()).decode()})
    alive = None
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            alive = "data" in json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        alive = e.code != 404
    except Exception:  # noqa: BLE001
        alive = None
    if alive is not None:
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            state[sid] = {"alive": alive, "checked_ts": int(now)}
            with open(cache_file + ".tmp", "w", encoding="utf-8") as f:
                json.dump(state, f)
            os.replace(cache_file + ".tmp", cache_file)
        except Exception:  # noqa: BLE001
            pass
    return alive


def axis_inbox_names():
    """Ось 3: имя файла inbox vs программно извлечённый frontmatter from."""
    problems = []
    if not os.path.isdir(INBOX):
        return problems
    for sid in os.listdir(INBOX):
        box = os.path.join(INBOX, sid)
        if not os.path.isdir(box):
            continue
        for fn in os.listdir(box):
            if not fn.endswith(".md"):
                continue
            m = re.search(r"__(ses_[A-Za-z0-9]+)\.md$", fn)
            if not m:
                continue
            file_sid = m.group(1)
            try:
                head = open(os.path.join(box, fn), encoding="utf-8").read(2000)
            except OSError:
                continue
            fm = re.search(r"^from:\s*(ses_[A-Za-z0-9]+)", head, flags=re.M)
            fm_sid = fm.group(1) if fm else ""
            if fm_sid and fm_sid != file_sid:
                problems.append({"axis": "inbox-names",
                                 "class": "name-vs-frontmatter",
                                 "sid": sid, "file": fn,
                                 "file_sid": file_sid, "fm_sid": fm_sid})
    return problems


def axes(which=(1, 2, 3)):
    out = []
    if 1 in which:
        out += axis_channel()
    if 2 in which:
        out += axis_claims()
    if 3 in which:
        out += axis_inbox_names()
    return out
