#!/usr/bin/env python3
"""waits — реестр осознанных ожиданий (задача «активное ожидание», слово
владельца 2026-10-27,via ИПТ).

Проблема (словом владельца): «нужно ждать осознанно, а я заметил, что это
зачастую пустые ожидания, которые тянутся днями, пока я не напишу». Решение:
ждём не молча, а записью. Каждая постановка «жду от X — Y» — строка в
append-only реестре; TTL просрочки превращает пустое ожидание в дефект
(класс «осечка ожидания»), а inbox каждый ход показывает просроченное.

Файл: ~/.local/share/ship-mail/waits.jsonl (рядом с почтой).
Команды:
  waits.py add --owe <sid> --what "..." [--by <sid>] [--ttl-minutes N]
               [--deadline-minutes N] [--ref R]
               [--type mandate|question|acceptance|pilot|external|proposal]
               [--state S] [--return-condition TEXT]
  waits.py done <id>            # ожидание снято (ответ получен/отказ)
  waits.py stitch <id> --reply-to <file|id> --answered-by <sid> \
              --answered-at <ISO> [--evidence TEXT]  # пришить ответ (Р-092)
  waits.py stitch-report        # ответы без пришивки (lag N), вне блока просрочки
  waits.py sweep [--ping]       # ответ есть -> stitch; нет ответа -> ping/escalate
  waits.py ping <id>            # пинок: каденс TTL удваивается (backoff до срока)
  waits.py autoping             # авто-пинг из цикла пробуждений (спека
                                # ic-waits-in-wake-cycle-20261107): каждой
                                # просроченной строке — письмо-пинок Р-090
                                # адресату + ping <id> (TTL растёт); не чаще
                                # одного пинга на строку за цикл ТТЛ; адресат
                                # owner — без авто-письма (письмо владельцу
                                # не автим)
  waits.py list [--all]
  waits.py overdue              # только просроченные (для inbox-блока)

Схема (решение ЦУ 2026-11-04, развитие механизма, не канон):
  type — mandate (default), question, acceptance, pilot, external, proposal;
  state — open (default), closed, rejected; proposal по умолчанию rejected;
  return_condition — что должно произойти, чтобы ожидание закрылось.
  Старые записи без type/state читаются как mandate/open.

TTL (Р-075, слово владельца 2026-11-03): единицы — МИНУТЫ.
Дефолт: 5 минут для всех; 10 минут для ses_eceb23a71ffeJO9QnFou8VngZC
(ЦУ, приёмки).

Модель (уточнение ЦУ 2026-11-03): TTL — это КАДЕНС пинка, а не дефект.
Срок/дедлайн живёт в тексте `what` (например, «до 04.11 утра») или в
необязательном `deadline_minutes`. Просрочка = пинок: работа идёт без
блокировки, `ping <id>` удваивает каденс (но не выше deadline_minutes,
если он задан). В overdue такие записи помечаются «пинок, не дефект».

Обратная совместимость: старые записи с ttl_hours читаются как
ttl_hours * 60 минут; новые записи хранят ttl_minutes.
Смена состояния (done) — событие, не молчание: строка уходит в done.jsonl.
"""
import argparse
import json
import os
import re
import time

HOME = os.environ.get("SHIP_MAIL_HOME") or os.path.expanduser(
    "~/.local/share/ship-mail")
WAITS = os.path.join(HOME, "waits.jsonl")
DONE = os.path.join(HOME, "waits-done.jsonl")
# Отправка авто-пингов: штатно — ship-mail.sh рядом со скриптом (единственный
# путь отправки, Р-028); selftest подменяет фейком через SHIP_MAIL_CMD.
SEND_CMD = os.environ.get("SHIP_MAIL_CMD") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "ship-mail.sh")
DEFAULT_TTL_MINUTES = 5
CU_TTL_MINUTES = 10
CU_SID = "ses_eceb23a71ffeJO9QnFou8VngZC"  # приёмки ЦУ — удлинённый TTL

# Схема ожиданий (решение ЦУ 2026-11-04, по ответу ИПТ через ЦСПМ):
# тип + состояние + условие возврата. Старые записи читаются как mandate/open.
WAIT_TYPES = ("mandate", "question", "acceptance", "pilot", "external", "proposal")
DEFAULT_TYPE = "mandate"
DEFAULT_STATE = "open"
# Потолок backoff: даже ожидание без дедлайна не пингуется чаще, чем раз в сутки
# (страховка от вечного цикла, если deadline_minutes забыли поставить).
MAX_TTL_MINUTES = 24 * 60


def _rows(path):
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    return out


def _append(path, row):
    os.makedirs(HOME, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _wid(row):
    return row.get("id") or "%08x" % abs(hash(json.dumps(
        row, sort_keys=True, ensure_ascii=False)) % (16 ** 8))


def _new_id():
    # уникальность: ms-метка + суффикс при коллизии (дефект 1: два add
    # в одну миллисекунду давали одинаковый id)
    base = int(time.time() * 1000) % (16 ** 8)
    existing = {r.get("id") for r in _rows(WAITS)} | {r.get("id") for r in _rows(DONE)}
    for n in range(4096):
        wid = "%08x" % ((base + n) % (16 ** 8))
        if wid not in existing:
            return wid
    raise SystemExit("waits: не удалось сгенерировать уникальный id")


def _ttl_minutes(row):
    """TTL строки в минутах; старые ttl_hours читаются как часы*60."""
    if row.get("ttl_minutes") is not None:
        return max(0, int(row["ttl_minutes"]))
    if row.get("ttl_hours") is not None:
        return max(0, int(row["ttl_hours"]) * 60)
    return DEFAULT_TTL_MINUTES


def _type(row):
    return row.get("type") or DEFAULT_TYPE


def _state(row):
    if row.get("state"):
        return row["state"]
    return "rejected" if _type(row) == "proposal" else DEFAULT_STATE


_DEADLINE_RE = re.compile(
    r"(до\s+\d{1,2}[./]\d{1,2}|\bдедлайн\b|\bсрок\b|\bутра\b|\bвечера\b|\b\d{1,2}:\d{2}\b)",
    re.IGNORECASE,
)


def _has_deadline(row):
    """Есть ли у ожидания срок/дедлайн, отличный от каденса пинка."""
    if row.get("deadline_minutes") is not None:
        return True
    if row.get("deadline"):
        return True
    return bool(_DEADLINE_RE.search(str(row.get("what", ""))))


def _rewrite_rows(rows):
    with open(WAITS, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def cmd_add(a):
    ref0 = getattr(a, "ref", "") or ""
    # Дедупликация (У-7, дефект найден живьём): ручная строка и авто-строка
    # ship-mail send --task с одним ref создавали две строки на одно дело,
    # и адресат получал два пинка. Активная (open) строка с тем же ref+owe
    # на это дело уже есть -> повтор не плодит строку.
    if ref0:
        for r in _rows(WAITS):
            if (str(r.get("ref") or "") == ref0
                    and str(r.get("who_owes") or "") == str(a.owe)
                    and _state(r) == "open"):
                print(f"WAIT-SKIP {r.get('id')}: дело ref '{ref0}' уже стоит "
                      f"в очереди у {a.owe} ({_state(r)}) — дубль не создаём")
                return 0
    if getattr(a, "ttl_minutes", 0):
        ttl = int(a.ttl_minutes)
    elif getattr(a, "ttl_hours", 0):
        # обратная совместимость: старый флаг, на входе часы
        ttl = int(a.ttl_hours) * 60
    else:
        ttl = CU_TTL_MINUTES if a.owe == CU_SID else DEFAULT_TTL_MINUTES
    wtype = getattr(a, "type", None) or DEFAULT_TYPE
    state = getattr(a, "state", "") or ("rejected" if wtype == "proposal" else DEFAULT_STATE)
    row = {"id": _new_id(),
           "who_waits": a.by or "ses_ece7b76c8ffeOkYZqZe38QbTVx",
           "who_owes": a.owe, "what": a.what, "ref": a.ref or "",
           "type": wtype, "state": state,
           "return_condition": getattr(a, "return_condition", "") or "",
           "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "since_ts": int(time.time()), "ttl_minutes": ttl}
    if getattr(a, "deadline_minutes", 0):
        row["deadline_minutes"] = int(a.deadline_minutes)
    _append(WAITS, row)
    extra = f", дедлайн {row['deadline_minutes']}м" if "deadline_minutes" in row else ""
    print(f"WAIT {row['id']} [{wtype}/{state}]: ждём от {a.owe}: {a.what} (TTL {ttl}м{extra})")


def cmd_done(wid):
    rows = _rows(WAITS)
    hit = [r for r in rows if r.get("id") == wid]
    if not hit:
        # id нет в активных: возможно, уже закрыт раньше (повторный done) —
        # честный ответ вместо «не найдено» (дефект 1, ИЦ 2026-10-31)
        closed = [r for r in _rows(DONE) if r.get("id") == wid]
        if closed:
            print(f"waits: ожидание {wid} уже закрыто "
                  f"({closed[0].get('closed', '?')}) — повтор не нужен")
            return 0
        print(f"waits: ожидание {wid} не найдено")
        return 1
    rest = [r for r in rows if r.get("id") != wid]
    with open(WAITS, "w", encoding="utf-8") as f:
        for r in rest:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    hit[0]["state"] = "closed"
    hit[0]["closed"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _append(DONE, hit[0])
    print(f"DONE {wid}: ожидание снято")
    return 0


def cmd_ping(wid):
    """Пинок: каденс удваивается до потолка; дедлайн — не потолок TTL.

    Дефект 11.11 (флуд 100 писем): при deadline_minutes == ttl_minutes
    min(old*2, deadline) возвращал ТОТ ЖЕ TTL — backoff не рос, пинг
    повторялся вечно каждые deadline минут. Теперь:
      - TTL растёт до MAX_TTL_MINUTES (сутки), дедлайн его не замораживает;
      - достигнутый дедлайн помечается escalated — строка уходит человеку,
        авто-пинги по ней прекращаются (см. cmd_autoping).
    """
    rows = _rows(WAITS)
    hit = [r for r in rows if r.get("id") == wid]
    if not hit:
        print(f"waits: ожидание {wid} не найдено")
        return 1
    row = hit[0]
    old = _ttl_minutes(row)
    new = max(1, min(old * 2, MAX_TTL_MINUTES))
    dl = _deadline(row)
    # Дедлайн — срок исполнения ОТ ОТКРЫТИЯ (канон waits-registry), поэтому
    # сравниваем с фактическим возрастом строки, а не с очередным TTL:
    # иначе задание с ttl=15/deadline=30 эскалировалось бы через 15 минут.
    age_min = (time.time() - int(row.get("since_ts") or time.time())) / 60.0
    if dl is not None and age_min >= dl:
        if not row.get("escalated"):
            row["escalated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            row["escalate_to"] = row.get("escalate_to") or "owner"
            print(f"PING {wid}: TTL {old}м достиг дедлайна {dl}м — ЭСКАЛАЦИЯ "
                  f"к {row['escalate_to']}: авто-пинги по строке прекращены")
    else:
        print(f"PING {wid}: TTL {old}м -> {new}м (пинок, не дефект)")
    row["ttl_minutes"] = new
    row["pinged"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    row["ping_count"] = int(row.get("ping_count", 0)) + 1
    _rewrite_rows(rows)
    return 0


def _deadline(row):
    """Дедлайн строки в минутах от since; None — не задан."""
    dl = row.get("deadline_minutes")
    if dl is None:
        return None
    try:
        dl = int(dl)
    except (TypeError, ValueError):
        return None
    return dl if dl > 0 else None


# --- Два времени строки (аудит Школы 2026-11-07, sha 9ccec4db41f5a500) ---
# since  — когда строка создана (шкала пинков);
# event_at — когда событие свершается. До event_at строка event-pending:
# просрочки нет, пинг не идёт (event-pending доминирует над TTL).
# Строки Корабля ведутся в MSK (+03): смещение явное, чтобы epoch не зависел
# от машины и от TZ процесса.
EVENT_TZ_HOURS = int(os.environ.get("WAITS_EVENT_TZ", "3"))

_PAT_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})[T ](\d{1,2}):(\d{2})")
_PAT_DMY = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})")
_PAT_DM = re.compile(r"\b(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{2})\b")


def _event_at(row, now=None):
    """Epoch момента события (или None). Явное поле event_at важнее парсинга.

    Парсинг консервативный: только явные формы даты-времени, и только если
    момент ещё не наступил (иначе это не «будущее событие», а факт/шум).
    Возвращает (epoch, source) либо (None, "").
    """
    import calendar
    import datetime as _dt

    now = time.time() if now is None else now
    tz = _dt.timezone(_dt.timedelta(hours=EVENT_TZ_HOURS))

    def _local_ts(value):
        """ISO -> epoch; без tz-смещения трактуем как MSK (строки Корабля)."""
        try:
            dt = _dt.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt.timestamp()

    raw = row.get("event_at")
    ts = _local_ts(raw) if raw else None
    # Явное поле тоже должно быть В БУДУЩЕМ: прошедшая дата — это факт,
    # а не план; иначе event-pending навсегда прячет просрочку.
    if ts is not None and ts > now:
        return ts, "event_at"

    text = " ".join(str(row.get(k) or "") for k in ("what", "return_condition"))
    m = _PAT_ISO.search(text)
    if m:
        y, mo, d, hh, mm = (int(x) for x in m.groups())
        try:
            dt = _dt.datetime(y, mo, d, hh, mm, tzinfo=tz)
            ts = dt.timestamp()
            if ts > now:
                return ts, "what(iso)"
        except ValueError:
            pass
    m = _PAT_DMY.search(text)
    if m:
        d, mo, y, hh, mm = (int(x) for x in m.groups())
        try:
            ts = _dt.datetime(y, mo, d, hh, mm, tzinfo=tz).timestamp()
            if ts > now:
                return ts, "what(date)"
        except ValueError:
            pass
    m = _PAT_DM.search(text)
    if m:
        d, mo, hh, mm = (int(x) for x in m.groups())
        # Без года — только ближайшее будущее В ЭТОМ году. Гадать «через год»
        # нельзя: любая прошедшая дата притворилась бы планом и спрятала
        # просрочку (дефект дня 08.11). Событие дальше года — с годом в тексте.
        try:
            ts = _dt.datetime(_dt.datetime.now(tz).year, mo, d, hh, mm,
                              tzinfo=tz).timestamp()
        except ValueError:
            ts = None
        if ts is not None and ts > now:
            return ts, "what(dm)"
    return None, ""


def _is_event_pending(row, now=None):
    """Event-pending: событие ещё не наступило -> не просрочка (доминирует)."""
    ts, _src = _event_at(row, now)
    return ts is not None


def _parse_ts(value):
    """ISO-строка -> epoch; сбой -> None (не выдумываем лаг)."""
    if not value:
        return None
    try:
        import datetime as _dt
        raw = str(value).strip()
        # допускаем Z и +03:00: datetime.fromisoformat Z не ест в 3.10-
        raw = raw.replace("Z", "+00:00")
        dt = _dt.datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        return dt.timestamp()
    except Exception:  # noqa: BLE001
        return None


def _overdue(row):
    age_min = (time.time() - row.get("since_ts", 0)) / 60.0
    if _type(row) == "proposal" or _state(row) != "open":
        return False, age_min
    # event-pending доминирует над TTL: до наступления события просрочки нет
    # (дефект дня 08.11: since+ttl считал возраст от первой даты и врал «просрочено»).
    if _is_event_pending(row):
        return False, age_min
    return age_min > _ttl_minutes(row), age_min


def cmd_stitch(a):
    """Пришить ответ: ответ есть, но wait ещё открыт.

    Append-only строка в waits-done:
      op=stitch, reply_to, answered_by, answered_at, stitched_at,
      lag_minutes, evidence, state=answered.
    """
    rows = _rows(WAITS)
    hit = [r for r in rows if r.get("id") == a.wid]
    recover = bool(getattr(a, "recover", False))
    if not hit:
        done = [r for r in _rows(DONE) if r.get("id") == a.wid]
        stitched = [r for r in done if r.get("op") in ("stitch", "stitch-recovery")]
        if stitched:
            print(f"waits: ожидание {a.wid} уже пришито "
                  f"({stitched[0].get('op')}, {stitched[0].get('stitched_at', '?')}) "
                  f"— повтор не нужен")
            return 0
        if not done:
            print(f"waits: ожидание {a.wid} не найдено")
            return 1
        if not recover:
            # Дефект, найденный живьём (письмо Храма 1173282c815c, 11.11):
            # закрытие без пришивки возможно, а штатного восстановления не было —
            # восстановительные записи делали в обход инструмента.
            print(f"waits: ожидание {a.wid} закрыто БЕЗ пришивки "
                  f"({done[0].get('state', '?')}, {done[0].get('closed', '?')}). "
                  f"Штатное восстановление: stitch {a.wid} --recover "
                  f"--evidence <чем доказан ответ> --authorized-by <кто санкционировал> "
                  f"--answered-at <ISO>")
            return 3
        evidence = (getattr(a, "evidence", "") or "").strip()
        authorized = (getattr(a, "authorized_by", "") or "").strip()
        if not evidence or not authorized:
            print("waits: --recover требует --evidence и --authorized-by "
                  "— восстановление без доказательства и санкции не пишется")
            return 2
        answered_ts = _parse_ts(a.answered_at)
        if answered_ts is None:
            print(f"waits: не разбираю answered_at={a.answered_at!r} — формат ISO")
            return 2
        base = dict(done[0])
        since_ts = int(base.get("since_ts") or int(time.time()))
        lag_min = round((answered_ts - since_ts) / 60.0, 1)
        base.update({
            "op": "stitch-recovery",
            "reply_to": a.reply_to or base.get("ref", ""),
            "answered_by": a.answered_by or base.get("who_owes", ""),
            "answered_at": a.answered_at,
            "stitched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "lag_minutes": lag_min,
            "evidence": evidence,
            "authorized_by": authorized,
            "recovery": True,
            "state": "answered",
            "sweep_lag_defect": lag_min > 60,
        })
        _append(DONE, base)  # append-only: прежние записи не переписываются
        print(f"RECOVER {a.wid}: пришито штатно, append-only "
              f"(санкция: {authorized}; lag {lag_min}м)")
        return 0
    row = hit[0]
    answered_ts = _parse_ts(a.answered_at)
    if answered_ts is None:
        print(f"waits: не разбираю answered_at={a.answered_at!r} — формат ISO")
        return 2
    since_ts = int(row.get("since_ts") or int(time.time()))
    lag_min = round((answered_ts - since_ts) / 60.0, 1)
    stitched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    row.update({
        "op": "stitch",
        "reply_to": a.reply_to or "",
        "answered_by": a.answered_by or "",
        "answered_at": a.answered_at,
        "stitched_at": stitched_at,
        "lag_minutes": lag_min,
        "evidence": a.evidence or "",
        "state": "answered",
        "closed": stitched_at,
        "op_deadline_minutes": 24 * 60,
        "sweep_lag_defect": lag_min > 60,
    })
    rest = [r for r in rows if r.get("id") != a.wid]
    _rewrite_rows(rest)
    _append(DONE, row)
    print(f"STITCH {a.wid}: ответ пришит, lag {lag_min}м "
          f"(from {row.get('who_owes')}, reply_to {row.get('reply_to')})")
    if lag_min > 60:
        print(f"SWEEP LAG-DEFECT {a.wid}: lag {lag_min}м > 60м "
              f"(дефект детектора, Р-093)")
    return 0


def cmd_stitch_report(_a=None):
    """Строчки «ответ без пришивки»: stitch-closed вне блока просрочки."""
    n = 0
    now = time.time()
    for r in _rows(DONE):
        if r.get("op") != "stitch" or _state(r) != "answered":
            continue
        stitched_ts = _parse_ts(r.get("stitched_at"))
        if stitched_ts is None:
            continue
        deadline = r.get("op_deadline_minutes") or 24 * 60
        try:
            deadline = int(deadline)
        except Exception:
            deadline = 24 * 60
        age_minutes = (now - stitched_ts) / 60.0
        if age_minutes >= deadline:
            continue
        n += 1
        print(f"ОТВЕТ БЕЗ ПРИШИВКИ (lag {r.get('lag_minutes')}м) {r.get('id')} "
              f"| ответил {r.get('answered_by')} | reply_to {r.get('reply_to')} "
              f"| {str(r.get('what'))}")
    print(f"STITCH-REPORT {n}")
    return 0


def _reply_files(sid):
    base = os.path.join(HOME, "inbox", sid)
    out = []
    for d in (base, os.path.join(base, "read")):
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(".md"):
                out.append(os.path.join(d, name))
    return out


def _frontmatter(path):
    data = {}
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return data
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return data
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        data[k.strip()] = v.strip().strip('"')
    return data


def _detect_reply(row):
    """Есть ли ответ: письмо от who_owes в ящик who_waits не ранее since."""
    since = int(row.get("since_ts") or 0)
    owe = row.get("who_owes") or ""
    waiter = row.get("who_waits") or ""
    for f in _reply_files(waiter):
        meta = _frontmatter(f)
        if meta.get("from") != owe:
            continue
        ts = _parse_ts(meta.get("ts"))
        if ts is None or ts < since:
            continue
        return meta.get("ts"), os.path.basename(f)
    return None, None


def cmd_sweep(a):
    """TTL-sweep: ответ есть -> stitch; ответа нет -> ping/escalate hint."""
    rows = _rows(WAITS)
    for r in rows:
        if _type(r) == "proposal" or _state(r) != "open":
            continue
        answered_at, reply = _detect_reply(r)
        if answered_at:
            class _A:  # простейший аргумент-объект для cmd_stitch
                pass
            args = _A()
            args.wid = r.get("id")
            args.reply_to = reply
            args.answered_by = r.get("who_owes") or ""
            args.answered_at = answered_at
            args.evidence = "auto-sweep: reply found in inbox"
            cmd_stitch(args)
            continue
        od, age = _overdue(r)
        if od:
            if a.ping:
                cmd_ping(r)
            print(f"SWEEP NO-ANSWER {r.get('id')}: {_age_label(age)} без ответа "
                  f"| ping/escalate к {r.get('who_owes')} | {str(r.get('what'))}")
        else:
            print(f"SWEEP WAITING {r.get('id')}: {_age_label(age)} без ответа, "
                  f"TTL ещё не вышел")
    return 0


def _age_label(minutes):
    if minutes >= 120:
        return f"{minutes:.0f}м ({minutes / 60:.1f}ч)"
    return f"{minutes:.0f}м"


def cmd_list(a):
    for r in _rows(WAITS):
        od, age = _overdue(r)
        wtype, state = _type(r), _state(r)
        if wtype == "proposal":
            mark = "предложение"
        elif state != "open":
            mark = state
        else:
            ev_ts, _src = _event_at(r)
            if ev_ts is not None:
                mark = "event-pending до " + time.strftime(
                    "%d.%m %H:%M", time.localtime(ev_ts))
            else:
                mark = "ПРОСРОЧЕНО" if od else "в ожидании"
                if od and _has_deadline(r):
                    mark += " (пинок)"
        ttl = _ttl_minutes(r)
        print(f"{r['id']} [{wtype}/{state}] {mark} {_age_label(age)}/{ttl}м  "
              f"{r['who_owes']}  {r['what']}")
    return 0


def cmd_overdue(a):
    n = 0
    for r in _rows(WAITS):
        od, age = _overdue(r)
        if od:
            n += 1
            ttl = _ttl_minutes(r)
            kind = " (пинок, не дефект; дедлайн в what)" if _has_deadline(r) else ""
            print(f"ПРОСРОЧЕНО {r['id']} [{_type(r)}]: {_age_label(age)} > TTL {ttl}м{kind} "
                  f"| ждём от {r['who_owes']} | {r['what'][:70]}")
    print(f"WAITS-OVERDUE {n}")
    return 0


PINGS = os.path.join(HOME, "waits-pings.jsonl")


def _self_sids():
    """Свои линии: письмо самому себе = подмена отправителя (Р-028), не шлём.

    Источник: OPENCODE_SESSION_ID текущего процесса + SHIP_MAIL_SELF_SID
    (список через запятую, для линий-двойников и релеев).
    """
    out = set()
    for var in ("SHIP_MAIL_SELF_SID", "OPENCODE_SESSION_ID"):
        raw = (os.environ.get(var) or "").strip()
        for part in re.split(r"[,\s]+", raw):
            if part.startswith("ses_"):
                out.add(part)
    return out


def _ping_text(row, age_min, ttl_min):
    """Письмо-пинок Р-090: три раздела + строка продолжения работы.

    Содержимое детерминировано из самой строки ожидания: модель не участвует,
    домыслов нет.
    """
    wid = row.get("id", "?")
    what = str(row.get("what") or "").strip()
    ret = str(row.get("return_condition") or "ответ строкой").strip()
    ref = str(row.get("ref") or "").strip()
    since = str(row.get("since") or "").strip()
    dlm = row.get("deadline_minutes")
    extra = f"\n- Дедлайн (минут от открытия): {dlm}" if dlm else ""
    ref_line = f"\n- Ref ожидания: {ref}" if ref else ""
    return (
        "## СДЕЛАНО\n"
        f"- Пинок по протоколу ожиданий: строка {wid} открыта {since}, "
        f"возраст {age_min:.0f}м > TTL {ttl_min}м, тип {_type(row)}. "
        "Это пинок, не дефект (Р-075).\n\n"
        f"## ЗАБЛОКИРОВАНО (ждём от {row.get('who_owes')})\n"
        f"- {what}\n"
        f"- Условие возврата: {ret}{extra}\n"
        f"- Канал ответа: письмо по ship-mail{ref_line}\n\n"
        "## ЖДЁТ-ЗАБОТЫ\n"
        "- Ответить строкой по существу; ожидание закрывается пришивкой "
        "(waits stitch), не молчанием.\n"
        "- TTL строки удвоен этим пинком (backoff, Р-075).\n\n"
        "После выполнения — продолжай свою работу. — авто-пинок реестра ожиданий\n"
    )


def _send_ping(row, text):
    """Отправка через ship-mail.sh (единственный путь, Р-028 rolling). -> rc, out

    ref уникален на каждый пинок: waits-autoping-<id>-<ping_count+1>.
    Фиксированный ref на строку реестра вечно ловил lint no-resend
    (sent.jsonl): rc!=0 -> cmd_ping не звался -> TTL не рос -> вечный FAIL.
    Инкремент ping_count делает cmd_ping уже после успешной отправки,
    поэтому в ref идёт значение ДО инкремента (+1).
    """
    import subprocess
    import tempfile
    fd, path = tempfile.mkstemp(prefix="autoping-", suffix=".md", dir="/tmp/opencode")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        r = subprocess.run(
            ["bash", SEND_CMD, "send",
             "--to", str(row.get("who_owes") or ""),
             "--from", str(row.get("who_waits") or ""),
             "--title", f"ПИНГ {row.get('id')}: ожидание просрочено",
             "--ref", f"waits-autoping-{row.get('id')}-{int(row.get('ping_count') or 0) + 1}",
             "--file", path],
            capture_output=True, text=True, timeout=90)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def cmd_autoping(a):
    """Авто-пинг просроченных ожиданий (спека ic-waits-in-wake-cycle-20261107).

    Правила:
      - только открытые строки; адресат не sid (owner и т.п.) — SKIP, письмо
        владельцу автоматически не шлём;
      - не чаще одного пинка на строку за цикл ТТЛ: прошло меньше текущего TTL
        с прошлого пинка — SKIP (повтор придёт на новом ТТЛ);
      - письмо ушло -> ping <id>: TTL удваивается (backoff, Р-075);
      - письмо не ушло -> TTL не растёт, факт в журнал, повторит следующий цикл.
    Метод программный: тело письма собирается из строки, модель не участвует.
    """
    rows = _rows(WAITS)
    now = int(time.time())
    self_sids = _self_sids()
    pinged = skipped = failed = overdue = 0
    for r in rows:
        od, age = _overdue(r)
        if not od:
            continue
        overdue += 1
        wid = r.get("id") or "?"
        owe = str(r.get("who_owes") or "")
        if r.get("escalated"):
            # Дедлайн исчерпан: строка уже эскалирована человеку (cmd_ping).
            # Авто-пинги по ней прекращены — иначе вечный цикл каждые TTL минут.
            print(f"AUTOPING SKIP {wid}: эскалирована к {r.get('escalate_to')} "
                  f"({r.get('escalated')}) — авто-пинги прекращены")
            skipped += 1
            continue
        if not owe.startswith("ses_"):
            print(f"AUTOPING SKIP {wid}: адресат '{owe}' — не сессия, письмо не шлём")
            skipped += 1
            continue
        if owe in self_sids:
            # Ждём от себя: письмо было бы подделкой отправителя и пустым ходом.
            # Механизм не спит — он зовёт линию работать (сигнал в stdout/sweep).
            print(f"AUTOPING SELF {wid}: ждём от своей линии ({owe}) — "
                  f"письмо не шлём, это моя работа: {str(r.get('what'))[:70]}")
            skipped += 1
            continue
        ttl = _ttl_minutes(r)
        prev = _parse_ts(r.get("pinged"))
        if prev is not None and (now - prev) < ttl * 60:
            print(f"AUTOPING SKIP {wid}: внутри цикла ТТЛ "
                  f"({(now - prev) / 60:.0f}м < {ttl}м)")
            skipped += 1
            continue
        if a.dry_run:
            print(f"AUTOPING DRY {wid} -> {owe}: {age:.0f}м > TTL {ttl}м")
            pinged += 1
            continue
        rc, out = _send_ping(r, _ping_text(r, age, ttl))
        if rc == 0:
            cmd_ping(wid)
            _append(PINGS, {"ts": now, "id": wid,
                            "to": owe, "from": str(r.get("who_waits") or ""),
                            "age_min": round(age), "rc": 0})
            print(f"AUTOPING OK {wid} -> {owe} ({age:.0f}м > TTL {ttl}м)")
            pinged += 1
        else:
            _append(PINGS, {"ts": now, "id": wid, "to": owe,
                            "age_min": round(age), "rc": rc})
            print(f"AUTOPING FAIL {wid} -> {owe} (rc={rc}): {out.strip()[:200]}")
            failed += 1
    print(f"AUTOPING: просрочено {overdue}, пинг {pinged}, "
          f"пропуск {skipped}, сбой {failed}")
    return 0 if failed == 0 else 1


def main():
    p = argparse.ArgumentParser(prog="waits")
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("add")
    a.add_argument("--owe", required=True)
    a.add_argument("--what", required=True)
    a.add_argument("--by", default="")
    a.add_argument("--type", choices=WAIT_TYPES, default=DEFAULT_TYPE,
                   help="тип ожидания (default: mandate)")
    a.add_argument("--state", default="",
                   help="состояние (default: open; proposal -> rejected)")
    a.add_argument("--return-condition", default="",
                   help="условие возврата: что должно произойти, чтобы ожидание закрылось")
    a.add_argument("--ttl-minutes", type=int, default=0)
    a.add_argument("--ttl-hours", type=int, default=0,
                   help="устаревший флаг, переводится в минуты")
    a.add_argument("--deadline-minutes", type=int, default=0,
                   help="срок исполнения в минутах от since; ограничивает backoff")
    a.add_argument("--ref", default="")
    d = sub.add_parser("done")
    d.add_argument("wid")
    st = sub.add_parser("stitch")
    st.add_argument("wid")
    st.add_argument("--reply-to", default="")
    st.add_argument("--answered-by", default="")
    st.add_argument("--answered-at", required=True,
                    help="ISO-время ответа (для lag)")
    st.add_argument("--evidence", default="")
    st.add_argument("--recover", action="store_true",
                    help="штатное восстановление строки, закрытой без пришивки "
                         "(требует --evidence и --authorized-by)")
    st.add_argument("--authorized-by", default="",
                    help="кто санкционировал восстановление (для --recover)")
    sub.add_parser("stitch-report")
    sw = sub.add_parser("sweep")
    sw.add_argument("--ping", action="store_true",
                    help="на просроченном без ответа — применить пинок TTL")
    pi = sub.add_parser("ping")
    pi.add_argument("wid")
    ap_ = sub.add_parser("autoping")
    ap_.add_argument("--dry-run", action="store_true",
                     help="только показать, писем не слать")
    sub.add_parser("list")
    sub.add_parser("overdue")
    args = p.parse_args()
    if args.cmd == "add":
        cmd_add(args)
    elif args.cmd == "done":
        return cmd_done(args.wid)
    elif args.cmd == "stitch":
        return cmd_stitch(args)
    elif args.cmd == "stitch-report":
        return cmd_stitch_report(args)
    elif args.cmd == "sweep":
        return cmd_sweep(args)
    elif args.cmd == "ping":
        return cmd_ping(args.wid)
    elif args.cmd == "overdue":
        return cmd_overdue(args)
    elif args.cmd == "autoping":
        return cmd_autoping(args)
    else:
        return cmd_list(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
