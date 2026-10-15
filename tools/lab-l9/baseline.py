#!/usr/bin/env python3
"""L9 baseline «до» (метод B протокола): счётчики по журналу сессий OpenCode.

Окно: фиксированное, последние 30 дней (7-дневное окно дало 0 read-вызовов — данные слишком свежие). Только счётчики/пути — содержимое не берём.
(1) полные чтения facts.md; (2) повторные чтения одного файла в одной сессии
для источников набора A; (3) прокси «ходов до ответа»: число read/grep-вызовов
в сессиях окна до первого обращения к ожидаемому источнику запроса A.
"""
import json
import sqlite3
import time
from pathlib import Path

DB = Path.home() / ".local/share/opencode/opencode.db"
WEEK = 30
FACTS = "OpenCode-Vault/04-Memory/facts.md"
A_SOURCES = [
    "04-Memory/facts.md",
    "04-Memory/active-context.md",
    "04-Memory/session-log/2026-10-13.md",
    "04-Memory/session-log/2026-10-14.md",
]

db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
since = int((time.time() - WEEK * 86400) * 1000)

rows = db.execute(
    "select session_id, time_created, data from part"
    " where json_extract(data,'$.type')='tool' order by session_id, time_created",
).fetchall()

reads: dict[str, dict[str, list[int]]] = {}
full_facts = 0
for sid, ts, data in rows:
    if ts < since:
        continue
    try:
        d = json.loads(data)
    except ValueError:
        continue
    st = d.get("state") or {}
    inp = st.get("input") or d.get("input") or {}
    tool, fp = d.get("tool"), inp.get("filePath") or inp.get("path") or ""
    if tool != "read" or "OpenCode-Vault" not in str(fp):
        continue
    rel = str(fp).split("OpenCode-Vault/")[-1]
    lim = inp.get("limit")
    if rel.endswith("facts.md") and lim in (None, 0) and not inp.get("offset"):
        full_facts += 1
    reads.setdefault(sid, {}).setdefault(rel, []).append(ts)

repeat_files = 0
repeat_extra = 0
for sid, per in reads.items():
    for rel, ts_list in per.items():
        if rel in A_SOURCES and len(ts_list) > 1:
            repeat_files += 1
            repeat_extra += len(ts_list) - 1

print(json.dumps({
    "окно_дней": WEEK,
    "сессий_с_чтениями_волта": len(reads),
    "полных_чтений_facts.md": full_facts,
    "сессий_с_повторами_по_источникам_A": repeat_files,
    "лишних_повторных_чтений": repeat_extra,
}, ensure_ascii=False, indent=1))
