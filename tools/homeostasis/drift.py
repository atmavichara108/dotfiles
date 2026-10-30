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


def axis_claims():
    """Ось 2: активные claims (ledger) вне peer-registry."""
    problems = []
    if not os.path.exists(LEDGER):
        return problems
    reg = registry_ids()
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
        if sid and sid not in reg:
            problems.append({"axis": "claims",
                             "class": "claim-outside-registry",
                             "sid": sid, "ref": d.get("ref", ""),
                             "edge": d.get("edge", ""),
                             "note": note[:120]})
    return problems


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
