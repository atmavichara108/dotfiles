#!/usr/bin/env python3
"""follower — «Следопыт»: read-only агрегат постановок (мандат ЦУ 2026-11-01).

Один экран «где всё и на какой стадии»: читает существующие файлы
(quests, TASKS, waits, session-log, decision-registry, goals), каждой строке
даёт ровно одно из четырёх состояний (зафиксировано / в работе / ждёт слова /
закрыто), поднимает сигналы стагнации, печатает одну страницу + одну
машиночитаемую строку. НИЧЕГО не пишет в источники (Р-056).

Состояния (канон ЦУ):
  зафиксировано — записано, не начато (ready/backlog/parked/Р-Д-строка решения)
  в работе      — активно (active/in_progress/🟡)
  ждёт слова    — ожидание чужого действия/слова (blocked/locked/waits/paused)
  закрыто       — завершено с evidence (done/dropped/✅/запись решения в каноне)

Сигналы (пороги в ~/.local/state/opencode/follower.json):
  wait_hours (48)  — ожидание старше порога
  idle_days  (7)   — «в работе», но не упоминалось в session-log столько дней
  overdue          — TTL ожидания исчерпан (сразу, порог не нужен)

Р-095 produced-annotations (регистр):
  - append-only logs/follower/produced-annotations.jsonl; источники не правим;
  - поля: addressee/sort/ticket/action/since/ready (ready — производная, не статус);
  - приоритет адресата: waits who_owes > явный текст > парсинг; конфликт — «неоднозначен»;
  - расхождение метки с источником — отдельная строка stale-meta, история не переписывается;
  - счёт: готово N / не готово M / не к владельцу K / БЕЗ МЕТКИ: X.

Строка без состояния = дефект агрегатора → секция UNSTATED, rc=2.

Использование:
  follower.py              # страница для человека
  follower.py --json-line   # + одна машиночитаемая строка в stdout
  rc: 0 ок · 2 есть UNSTATED · 1 ошибка источника
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sys

HOME = os.path.expanduser("~")
VAULT = os.path.join(HOME, "Projects/OpenCode-Vault")
QUESTS = os.path.join(VAULT, "11-Quests/quests.md")
TASKS = os.path.join(VAULT, "TASKS.md")
REGISTRY = os.path.join(VAULT, "docs/org/decision-registry.md")
SESSION_LOG = os.path.join(VAULT, "04-Memory/session-log")
# v0.2 (замечание ЦУ 2026-11-01): worktree таскают СВОИ копии волта и
# session-reports — читаем все, иначе живые линии вне волта дают ложные
# «нет упоминаний». Только чтение, порядок: волт первым, worktree — поверх.
SESSION_GLOBS = [
    SESSION_LOG,
    os.path.join(VAULT, "04-Memory/session-reports"),
    os.path.join(HOME, "Projects/OpenCode-Vault-tasks/*/04-Memory/session-log"),
    os.path.join(HOME, "Projects/OpenCode-Vault-tasks/*/04-Memory/session-reports"),
    os.path.join(HOME, "Projects/dotfiles-tasks/*/.opencode/memory/session-reports"),
    os.path.join(HOME, "Projects/dotfiles-tasks/*/.opencode/memory/session-log"),
]
WAITS = os.path.join(HOME, ".local/share/ship-mail/waits.jsonl")
WAITS_DONE = os.path.join(HOME, ".local/share/ship-mail/waits-done.jsonl")
GOALS = os.path.join(HOME, ".local/state/opencode/goal.json")
GOAL_DIR = os.path.join(HOME, ".local/state/opencode/goals")
CONF = os.path.join(HOME, ".local/state/opencode/follower.json")
# Р-095: отдельный append-only регистр производных пометок. Источники не правим.
ANNOTATIONS = os.path.join(HOME, "dotfiles/logs/follower/produced-annotations.jsonl")

ST_FIXED = "зафиксировано"
ST_WORK = "в работе"
ST_WAIT = "ждёт слова"
ST_DONE = "закрыто"
STATES = (ST_FIXED, ST_WORK, ST_WAIT, ST_DONE)

DEFAULT_CONF = {"wait_hours": 48, "idle_days": 7}


def load_conf():
    try:
        with open(CONF, encoding="utf-8") as f:
            c = json.load(f)
        return {**DEFAULT_CONF, **c}
    except FileNotFoundError:
        os.makedirs(os.path.dirname(CONF), exist_ok=True)
        with open(CONF, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONF, f, ensure_ascii=False, indent=2)
        return dict(DEFAULT_CONF)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONF)


def row(id_, source, title, state, owner="", note="", evidence=""):
    # sort/вопрос-готов (Р-092/ttl-sweep): строки «ждёт слова» классифицируются
    # сортом ЖДУ; вопрос-готов = сорту ЖДУ есть кому задать (owner) и о чём
    # (title+note). Нет выдуманных владельцев/текстов.
    is_wait = state == ST_WAIT
    question_ready = bool(is_wait and owner and title and note)
    return {"id": id_, "source": source, "title": title, "state": state,
            "owner": owner, "note": note, "evidence": evidence,
            "sort": "ЖДУ" if is_wait else None,
            "question_ready": question_ready}


def read_text(path, problems):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        problems.append(f"{path}: {e}")
        return ""


# ---------- Р-095: produced-annotations (производные метки, не статус) ----

SID_RE = re.compile(r"\bses_[A-Za-z0-9]+\b")
OWNER_RE = re.compile(r"(владелец|хозяин|владельца|owner|rudra)", re.IGNORECASE)
STALE_RE = re.compile(r"(нет ответа|не отвеч|просроч|пинок|молч|непришит|мимо)",
                      re.IGNORECASE)
PROMISE_RE = re.compile(r"(обеща|слот|до \d|позже|потом|ожида)", re.IGNORECASE)
ACTION_RE = re.compile(r"(апрув|подтвер|да/нет|да или нет|принять|пришить|ответить)",
                       re.IGNORECASE)
TICKET_RE = re.compile(r"^(?:Q-\d+(?:\.\d+)?|T-\d+|Р-Д-\d+|Р-\d+)$")


def _annotation_text(row):
    return " ".join([
        str(row.get("title") or ""),
        str(row.get("note") or ""),
        str(row.get("return_condition") or ""),
        str(row.get("ticket_ref") or ""),
    ])


def _detect_addressee(row):
    """Приоритет: waits who_owes > явный текст > парсинг. Конфликт — не молчание."""
    owner = str(row.get("owner") or "").strip()
    text = _annotation_text(row)
    explicit_owner = bool(OWNER_RE.search(text))
    sids = SID_RE.findall(text)
    if row.get("source") == "waits" and owner:
        if explicit_owner and owner != "owner":
            return "неоднозначен", "waits-who_owes-vs-text-owner"
        return owner, "waits:who_owes"
    if explicit_owner and sids:
        return "неоднозначен", "text-owner-and-session"
    if explicit_owner:
        return "owner", "text:owner"
    if owner:
        return owner, "parsed:owner"
    if len(set(sids)) == 1:
        return sids[0], "text:session"
    if len(set(sids)) > 1:
        return "неоднозначен", "multiple-sessions-in-text"
    return "", "no-addressee"


def _detect_sort(row, addressee):
    if not addressee or addressee == "неоднозначен":
        return "БЕЗ МЕТКИ"
    if addressee == "owner":
        return "корень"
    text = _annotation_text(row)
    if STALE_RE.search(text):
        return "сторож"
    if PROMISE_RE.search(text):
        return "promise"
    return "сторож" if row.get("source") == "waits" else "promise"


def _detect_ticket(row):
    ticket_ref = str(row.get("ticket_ref") or "").strip()
    if ticket_ref:
        return ticket_ref, True
    rid = str(row.get("id") or "").strip()
    if TICKET_RE.match(rid):
        return rid, True
    return "", False


def _detect_action(row):
    text = _annotation_text(row)
    if ACTION_RE.search(text):
        return "одно действие"
    return "неявно"


def _parse_ts(value):
    if not value:
        return None
    try:
        raw = str(value).strip().replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.timestamp()
    except Exception:  # noqa: BLE001
        return None


def _time_now():
    return dt.datetime.now(dt.timezone.utc).timestamp()


def _ann_key(value):
    """Нормализация ID: `quests:Q-005.1` и `Q-005.1` — один ключ."""
    s = str(value or "").strip()
    for prefix in ("waits:", "wait:", "quests:", "tasks:", "TASKS:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s


def _annotation_core(row):
    addressee, basis = _detect_addressee(row)
    sort = _detect_sort(row, addressee)
    ticket, ticket_detected = _detect_ticket(row)
    action = _detect_action(row)
    since = str(row.get("since") or "").strip() or "unknown"
    reply = bool(row.get("reply") or row.get("stitch"))
    if reply:
        # Ответ/пришивка — приоритетная причина в аннотации.
        action = "ответ/пришивка"
    ambiguity = addressee == "неоднозначен"
    no_addressee = not addressee
    since_unknown = since == "unknown"
    ticket_unknown = not ticket_detected
    action_unknown = action == "неявно"
    ready = not any([ambiguity, no_addressee, since_unknown,
                     ticket_unknown, action_unknown])
    reason = ""
    if no_addressee:
        reason = "нет адресата"
    elif ambiguity:
        reason = "addressee неоднозначен"
    elif since_unknown:
        reason = "порог неизвестен"
    elif ticket_unknown:
        reason = "билет не размечен"
    elif action_unknown:
        reason = "действие неявно"
    elif reply:
        reason = "ответ/пришивка"
    meta_state = "no-meta" if sort == "БЕЗ МЕТКИ" else "marked"
    return {
        "id": _ann_key(row.get("id")),
        "source": row.get("source"),
        "addressee": addressee or "БЕЗ МЕТКИ",
        "sort": sort,
        "ticket": ticket,
        "action": action,
        "since": since,
        "ready": ready,
        "reason": reason,
        "addressee_basis": basis,
        "meta_state": meta_state,
        "meta_seen_ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "meta_by": "follower-rule",
        "evidence": f"{row.get('source')}:{row.get('id')}",
    }


def _load_annotations():
    if not os.path.exists(ANNOTATIONS):
        return {}
    out = {}
    try:
        for line in open(ANNOTATIONS, encoding="utf-8"):
            try:
                d = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(d, dict) and d.get("id"):
                out[_ann_key(d.get("id"))] = d
    except OSError:
        pass
    return out


def _same_annotation(old, new):
    keys = ("addressee", "sort", "ticket", "action", "since", "ready",
            "reason", "meta_state")
    return all(old.get(k) == new.get(k) for k in keys)


def _append_annotation(entry):
    os.makedirs(os.path.dirname(ANNOTATIONS), exist_ok=True)
    with open(ANNOTATIONS, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def produce_annotations(rows, extra_rows=None):
    """Производные пометки append-only; расхождение — отдельная stale-meta строка."""
    old_by_id = _load_annotations()
    annotations = []
    stale = []
    no_meta = []
    for r in list(rows) + list(extra_rows or []):
        if r.get("state") != ST_WAIT and not r.get("annotation_only"):
            continue
        core = _annotation_core(r)
        key = _ann_key(core["id"])
        old = old_by_id.get(key)
        # Дедлайн метки: нет метки 24ч от первого появления -> stale-meta.
        if core["meta_state"] == "no-meta":
            no_meta.append(core)
            first_seen = None
            if old and old.get("meta_seen_ts"):
                first_seen = _parse_ts(old.get("meta_seen_ts"))
            if old and first_seen and (_time_now() - first_seen) > 24 * 3600:
                stale.append({"op": "stale-meta", "id": core["id"],
                              "reason": "deadline-metki: 24ч без метки",
                              "first_seen": old.get("meta_seen_ts"),
                              "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                              "meta_by": "follower-rule"})
            elif not old:
                _append_annotation(core)
        elif old and not _same_annotation(old, core):
            stale.append({"op": "stale-meta", "id": core["id"],
                          "old": {k: old.get(k) for k in
                                  ("addressee", "sort", "ticket", "action",
                                   "since", "ready", "reason", "meta_state")},
                          "new": {k: core.get(k) for k in
                                  ("addressee", "sort", "ticket", "action",
                                   "since", "ready", "reason", "meta_state")},
                          "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                          "meta_by": "follower-rule"})
            _append_annotation(core)
        elif not old:
            _append_annotation(core)
        annotations.append(core)

    counts = {"N": 0, "M": 0, "K": 0, "X": 0, "stale-meta": len(stale),
              "reasons": {}}
    for a in annotations:
        if not a["addressee"] or a["addressee"] == "БЕЗ МЕТКИ":
            counts["X"] += 1
            rsn = a["reason"] or "нет метки"
        elif a["addressee"] == "owner":
            if a["ready"]:
                counts["N"] += 1
            else:
                counts["M"] += 1
                rsn = a["reason"] or "не готов"
        else:
            counts["K"] += 1
            rsn = "не к владельцу"
        counts["reasons"][rsn] = counts["reasons"].get(rsn, 0) + 1
    return annotations, counts, stale


# ---------- парсеры источников ----------

QUEST_STATUS = {"active": ST_WORK, "ready": ST_FIXED, "parked": ST_FIXED,
                "locked": ST_WAIT, "done": ST_DONE, "closed": ST_DONE,
                "cancelled": ST_DONE}
# locked: квест ждёт преусловия (слово владельца, другой квест) — это «ждёт слова»
# по построению: locked без условия ожидания в реестре не встречается.
# Составной статус (напр. «→ Q-009 (перекрыто) active»): берём первое
# вхождение известного слова — домыслы отсекаем, статусов в ячейке >1.


def parse_quests(problems, unstated):
    rows = []
    text = read_text(QUESTS, problems)
    if not text and not problems:
        return rows
    for line in text.splitlines():
        m = re.match(r"^\|\s*\*{0,2}(Q-[\d.]+)\*{0,2}\s*\|(.+)$", line)
        if not m:
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        if len(cells) < 5:
            unstated.append(f"quests:{m.group(1)}: {line[:70]}")
            continue
        qid, title, status = cells[0].strip("*"), cells[1], cells[2].lower()
        owner = cells[3] if len(cells) > 3 else ""
        # «ждёт слова» важнее машинного статуса в той же ячейке: составная
        # строка вроде «отчёт готов, ждёт слова владельца ... active»
        # принадлежит очереди ждущих, а не активной работе.
        if "ждёт слова" in status:
            state = ST_WAIT
        else:
            state = QUEST_STATUS.get(status)
        if state is None:
            # составной статус: первое известное слово из ячейки
            for w in sorted(QUEST_STATUS, key=status.find):
                if w in status and status.find(w) == min(
                        status.find(x) for x in QUEST_STATUS if x in status):
                    state, status = QUEST_STATUS[w], w
                    break
        if state is None:
            unstated.append(f"quests:{qid}: неизвестный статус {cells[2]!r}")
            continue
        rows.append(row(qid, "quests", title, state, owner=owner,
                        note=f"статус:{status}"))
    return rows


# секции TASKS.md: заголовок секции задаёт статус строк внутри
TASK_SECTION = {"🟡": ST_WORK, "⛔": ST_WAIT, "🟤": ST_FIXED,
                "✅": ST_DONE, "➖": ST_DONE}


def parse_tasks(problems, unstated):
    rows = []
    text = read_text(TASKS, problems)
    if not text and not problems:
        return rows
    section = None
    for line in text.splitlines():
        h = re.match(r"^##\s+(\S+)\s+(.*)$", line)
        if h:
            section = h.group(1)
            continue
        m = re.match(r"^\|\s*(T-\d+)\s*\|(.+)$", line)
        if not m:
            continue
        state = TASK_SECTION.get(section) if section else None
        tid = m.group(1)
        if state is None:
            unstated.append(f"tasks:{tid}: секция {section!r} не распознана")
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        title = re.sub(r"\*\*", "", cells[1]) if len(cells) > 1 else ""
        owner = cells[3] if len(cells) > 3 else ""
        ev = ""
        if state == ST_DONE:
            dm = re.search(r"[Dd]one\s+(\d{4}-\d{2}-\d{2})", title)
            ev = dm.group(0) if dm else "запись в секции Done"
        rows.append(row(tid, "TASKS", title, state, owner=owner,
                        note=f"секция:{section}", evidence=ev))
    return rows


def parse_waits(problems, now):
    rows = []
    try:
        with open(WAITS, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                w = json.loads(line)
                # waits.jsonl — активные ожидания: stitch/закрытые строки не очередь.
                if w.get("op") == "stitch" or w.get("state") not in (None, "open"):
                    continue
                age_h = (now - dt.datetime.fromisoformat(
                    w["since"].replace("Z", "+00:00")).timestamp()) / 3600 \
                    if "since" in w else None
                rows.append(row(w.get("id", "?"), "waits", w.get("what", ""),
                                ST_WAIT, owner=w.get("who_owes", ""),
                                note=f"age_h:{age_h:.0f}" if age_h is not None else "",
                                evidence=""))
                rows[-1]["age_h"] = age_h
                rows[-1]["ttl_hours"] = w.get("ttl_hours")
                rows[-1]["since"] = w.get("since")
                rows[-1]["ticket_ref"] = w.get("return_condition") or w.get("ref") or ""
                rows[-1]["return_condition"] = w.get("return_condition") or ""
    except FileNotFoundError:
        problems.append(f"waits: {WAITS} нет")
    except json.JSONDecodeError as e:
        problems.append(f"waits: битая строка JSONL — {e}")
    return rows


def parse_reply_annotations(problems, now=None):
    """Строки ответов/пришивок waits: только для produced-annotations.

    В активную очередь они не идут (they answered), но метку по исходному wait
    нужно переразметить: answer/reply — приоритетная причина.
    """
    rows = []
    for path in (WAITS, WAITS_DONE):
        if not os.path.exists(path):
            continue
        try:
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                try:
                    w = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if w.get("op") != "stitch" and w.get("state") != "answered":
                    continue
                rid = _ann_key(w.get("reply_to") or w.get("id"))
                if not rid:
                    continue
                answered_by = str(w.get("answered_by") or "").strip()
                # owner-фразировка из ответа: адресат-корень, не сессия.
                owner = "owner" if OWNER_RE.search(answered_by) else answered_by
                note = f"reply/lag {w.get('lag_minutes')}м"
                rows.append(row(rid, "waits", "ответ/пришивка", ST_WAIT,
                                owner=owner, note=note,
                                evidence=str(w.get("evidence") or "")[:70]))
                r = rows[-1]
                r["annotation_only"] = True
                r["reply"] = True
                r["stitch"] = True
                r["since"] = w.get("answered_at") or w.get("stitched_at") or ""
                r["ticket_ref"] = w.get("topic-key") or w.get("ref") or ""
                r["lag_minutes"] = w.get("lag_minutes")
        except OSError as e:
            problems.append(f"waits: {path}: {e}")
    return rows


def merge_reply_annotations(rows, reply_rows):
    """Ответ на активный wait обновляет его метку, не создавая вторую очередь."""
    by_key = {}
    for r in reply_rows:
        by_key[_ann_key(r.get("id"))] = r
    for r in rows:
        key = _ann_key(r.get("id"))
        rep = by_key.get(key)
        if rep and not r.get("reply"):
            r["reply"] = True
            r["stitch"] = True
            r["reply_by"] = rep.get("owner") or ""
            r["reply_lag_minutes"] = rep.get("lag_minutes")
            if not r.get("ticket_ref"):
                r["ticket_ref"] = rep.get("ticket_ref") or ""
            r["note"] = f"{r.get('note') or ''} + reply/lag {rep.get('lag_minutes')}м".strip()
    return rows


def parse_decisions(problems, unstated):
    rows = []
    text = read_text(REGISTRY, problems)
    if not text and not problems:
        return rows
    for line in text.splitlines():
        m = re.match(r"^\|\s*(Р-Д-\d+)\s*\|(.+)$", line)
        if not m:
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        if len(cells) < 4:
            unstated.append(f"decisions:{m.group(1)}: {line[:70]}")
            continue
        rid, date = cells[0], cells[1]
        executor = cells[-1]
        # решение записано в канон-реестр = закрыто; исполнение — отдельные
        # линии (TASKS/quests), в строке решения статуса исполнения нет.
        rows.append(row(rid, "decisions", cells[2][:90], ST_DONE,
                        owner=executor, note=f"слово:{date}",
                        evidence="запись в decision-registry"))
    return rows


def parse_goals(problems, unstated):
    rows = []
    GOAL_STATUS = {"active": ST_WORK, "paused": ST_WAIT, "done": ST_DONE,
                   "dropped": ST_DONE}

    def one(path, fallback_id):
        try:
            with open(path, encoding="utf-8") as f:
                g = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            problems.append(f"goals {path}: {e}")
            return
        status = g.get("status", "")
        state = GOAL_STATUS.get(status)
        gid = g.get("slug") or g.get("storage", "").split("/")[-1] \
            or g.get("session") or fallback_id
        if state is None:
            unstated.append(f"goals:{gid}: неизвестный статус {status!r}")
            return
        ev = ""
        if state == ST_DONE:
            e = g.get("evidence")
            if isinstance(e, list) and e:
                ev = str(e[-1])[:70]
            elif isinstance(e, str) and e:
                ev = e[:70]
        r = row(str(gid), "goals", (g.get("objective") or "")[:90], state,
                note=f"статус:{status}", evidence=ev)
        if "updated_at" in g:
            r["updated_at"] = g["updated_at"]
        rows.append(r)

    if os.path.exists(GOALS):
        one(GOALS, "goal-aggregate")
    for p in sorted(glob.glob(os.path.join(GOAL_DIR, "*.json"))):
        one(p, os.path.basename(p))
    return rows


# ---------- сигналы стагнации ----------

def load_last_seen(problems):
    """ID -> дата последнего упоминания в session-log (из имени файла).

    v0.2: обходит все SESSION_GLOBS — волт и worktree-копии; последнее
    упоминание побеждает (файлы обходятся по возрастанию даты)."""
    last = {}
    seen_any = False
    for pattern in SESSION_GLOBS:
        for d in sorted(glob.glob(pattern)):
            paths = sorted(glob.glob(os.path.join(d, "*.md")))
            if not paths and not os.path.isdir(d):
                continue
            seen_any = True
            for path in paths:
                m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
                date = m.group(1) if m else "0000-00-00"
                try:
                    with open(path, encoding="utf-8") as f:
                        text = f.read()
                except OSError:
                    continue
                for pid in set(re.findall(
                        r"\b(?:T-\d+|Q-[\d.]+|Р-Д-\d+)\b", text)):
                    if last.get(pid, "0000-00-00") < date:
                        last[pid] = date
    if not last:
        problems.append(
            "session-log: ни один источник из " + str(len(SESSION_GLOBS))
            + " гнёзд не дал упоминаний")
    return last


def signals(rows, last_seen, conf, now):
    out = []
    today = dt.date.fromtimestamp(now).isoformat()
    for r in rows:
        if r["source"] == "waits":
            age, ttl = r.get("age_h"), r.get("ttl_hours")
            if age is not None and ttl is not None and age > ttl:
                out.append({"id": r["id"], "reason":
                            f"просрочено ожидание {age:.0f}ч > TTL {ttl}ч"})
            elif age is not None and age > conf["wait_hours"]:
                out.append({"id": r["id"], "reason":
                            f"ожидание {age:.0f}ч > порога {conf['wait_hours']}ч"})
        elif r["state"] == ST_WORK and r["source"] in ("TASKS", "quests"):
            seen = last_seen.get(r["id"])
            if seen is None:
                out.append({"id": r["id"], "reason":
                            "в работе, но нет упоминаний в session-log"})
            else:
                idle = (dt.date.fromisoformat(today)
                        - dt.date.fromisoformat(seen)).days
                if idle > conf["idle_days"]:
                    out.append({"id": r["id"], "reason":
                                f"в работе, {idle}д без упоминаний "
                                f"(порог {conf['idle_days']}д)"})
        elif r["state"] == ST_WORK and r["source"] == "goals" \
                and r.get("updated_at"):
            try:
                upd = r["updated_at"][:10]
                idle = (dt.date.fromisoformat(today)
                        - dt.date.fromisoformat(upd)).days
                if idle > conf["idle_days"]:
                    out.append({"id": r["id"], "reason":
                                f"цель в работе, {idle}д без обновлений "
                                f"(порог {conf['idle_days']}д)"})
            except ValueError:
                pass
    return out


def half_done(rows, last_seen):
    """полпути: в работе и уже упоминалась — началась, но не закрыта."""
    return [r["id"] for r in rows
            if r["state"] == ST_WORK and r["id"] in last_seen]


def main():
    ap = argparse.ArgumentParser(description="Следопыт: read-only агрегат постановок")
    ap.add_argument("--json-line", action="store_true",
                    help="вывести одну машиночитаемую строку")
    args = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc).timestamp()
    conf = load_conf()
    problems, unstated = [], []
    rows = []
    rows += parse_quests(problems, unstated)
    rows += parse_tasks(problems, unstated)
    rows += parse_waits(problems, now)
    rows += parse_decisions(problems, unstated)
    rows += parse_goals(problems, unstated)
    reply_rows = parse_reply_annotations(problems, now)
    rows = merge_reply_annotations(rows, reply_rows)
    if problems and not rows:
        print("FATAL: источники недоступны: " + "; ".join(problems),
              file=sys.stderr)
        return 1

    annotations, a_counts, stale_meta = produce_annotations(rows, reply_rows)

    last_seen = load_last_seen(problems)
    sigs = signals(rows, last_seen, conf, now)
    half = half_done(rows, last_seen)

    by_state = {s: 0 for s in STATES}
    for r in rows:
        by_state[r["state"]] += 1

    waiting_rows = [r for r in rows if r["state"] == ST_WAIT]
    ready_rows = [r for r in waiting_rows if r.get("question_ready")]

    print(f"\n■ ЖДУ — вопросы (готовы {len(ready_rows)}/{len(waiting_rows)})")
    for r in ready_rows[:15]:
        print(f"  ? {r['source']} {r['id']}: {r['title'][:70]} "
              f"[{r['owner']}]")
    if len(ready_rows) > 15:
        print(f"  … и ещё {len(ready_rows) - 15}")

    print(f"\n■ PRODUCED-АННОТАЦИИ: готово {a_counts['N']} / "
          f"не готово {a_counts['M']} / не к владельцу {a_counts['K']} / "
          f"БЕЗ МЕТКИ: {a_counts['X']} / stale-meta {a_counts['stale-meta']}")
    for reason, n in sorted(a_counts["reasons"].items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  причина: {reason} — {n}")
    print(f"  реестр: {ANNOTATIONS}")

    no_meta_rows = [a for a in annotations if a.get("meta_state") == "no-meta"]
    print(f"\n■ МЕТКИ НЕТ — ждёт разметки ({len(no_meta_rows)})")
    for a in no_meta_rows[:15]:
        print(f"  ? {a['id']}: нет адресата/сорта — разметить "
              f"(deadline 24ч, иначе stale-meta)")
    if len(no_meta_rows) > 15:
        print(f"  … и ещё {len(no_meta_rows) - 15}")

    # ---- страница для человека ----
    print("СЛЕДОПЫТ — где всё и на какой стадии")
    print("=" * 72)
    for s in (ST_WORK, ST_WAIT, ST_FIXED, ST_DONE):
        group = [r for r in rows if r["state"] == s]
        print(f"\n■ {s.upper()} ({len(group)})")
        for r in group:
            own = f" [{r['owner']}]" if r["owner"] else ""
            note = f" ({r['note']})" if r["note"] else ""
            ev = f" → evidence: {r['evidence']}" if r["evidence"] else ""
            print(f"  {r['source']} {r['id']}: {r['title'][:70]}{own}{note}{ev}")
    print(f"\n■ СИГНАЛЫ ({len(sigs)})")
    for s in sigs:
        print(f"  ⚠ {s['id']}: {s['reason']}")
    if half:
        print(f"\n■ ПОЛПУТИ — начато, не закрыто ({len(half)}): "
              + ", ".join(half[:12]) + ("…" if len(half) > 12 else ""))
    if unstated:
        print(f"\n■ UNSTATED — без состояния ({len(unstated)}) — дефект агрегатора")
        for u in unstated:
            print(f"  ✗ {u}")
    if problems:
        print(f"\n■ ПРОБЛЕМЫ ИСТОЧНИКОВ ({len(problems)})")
        for p in problems:
            print(f"  ! {p}")
    print(f"\nИтого строк: {len(rows)} · без состояния: {len(unstated)} · "
          f"сигналов: {len(sigs)}")

    if args.json_line:
        payload = {
            "ts": dt.datetime.fromtimestamp(
                now, dt.timezone.utc).isoformat(timespec="seconds"),
            "tool": "follower-0.1",
            "total": len(rows), "stated": len(rows) - len(unstated),
            "unstated": len(unstated),
            "by_state": by_state,
            "alerts": sigs,
            "half_done": half,
            "waiting_questions": [
                {"id": r["id"], "source": r["source"], "title": r["title"],
                 "owner": r["owner"], "sort": "ЖДУ",
                 "question_ready": bool(r.get("question_ready"))}
                for r in rows if r["state"] == ST_WAIT
            ],
            "produced_annotations": annotations,
            "annotation_counts": a_counts,
            "stale_meta": stale_meta,
            "sources": [{"path": p, "ok": True} for p in
                        (QUESTS, TASKS, WAITS, REGISTRY)] +
                       [{"path": SESSION_LOG, "ok": not problems}],
        }
        print(json.dumps(payload, ensure_ascii=False))

    return 2 if unstated else 0


if __name__ == "__main__":
    sys.exit(main())
