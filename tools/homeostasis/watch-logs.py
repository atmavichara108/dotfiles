#!/usr/bin/env python3
"""watch-logs — сторож логов opencode: сбой → инцидент, а не тишина.

Мандат Р-031 (ЦУ, 2026-10-26): логи должны становиться сигналом. Читает
НОВЕЙШИЙ файл ~/.local/share/opencode/log/*.log с сохранённого смещения
(offset-state), ищет паттерны сбоев, каждую находку пишет append-only
записью в incidents.jsonl (меты + сниппет ≤200, без секретов). Повтор
одного и того же паттерна — не дубль диагностики: ссылка на первую
запись (seen.jsonl), новая диагностика только для нового хеша строки.

Ротация логов (файл на старт сервера): сменился файл — смещение сброшено,
факт ротации записан в журнал.

Запуск: systemd-юнит watch-logs.service (Restart=always) или вручную:
  python3 watch-logs.py            # один инкрементальный проход
  python3 watch-logs.py --status   # состояние и счётчики
"""
import hashlib
import json
import os
import sys
import time

LOG_DIR = os.path.expanduser("~/.local/share/opencode/log")
STATE_DIR = os.path.expanduser("~/.local/state/opencode/watch")
OFFSET_FILE = os.path.join(STATE_DIR, "offset.json")
SEEN_FILE = os.path.join(STATE_DIR, "seen.jsonl")
INCIDENTS_FILE = os.path.join(STATE_DIR, "incidents.jsonl")
SNIPPET_MAX = 200

# (класс, подстрока) — порядок = приоритет класса при нескольких совпадениях
PATTERNS = [
    ("drain-failed", "Failed to drain"),
    ("agent-not-found", "AgentNotFoundError"),
    ("refuse-channel", "REFUSE"),
    ("letter-failed", "event=failed"),
    ("dead-letter", "dead-letter"),
    ("env-invalid", "Invalid environment"),
    ("model-unavailable", "model unavailable"),
    ("quota", "usage limit exceeded"),
]


def newest_log():
    """Новейший файл лога (имя сортируемое). None если логов нет."""
    try:
        files = sorted(f for f in os.listdir(LOG_DIR) if f.endswith(".log"))
    except OSError:
        return None
    if not files:
        return None
    return os.path.join(LOG_DIR, files[-1])


def load_offset():
    try:
        with open(OFFSET_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        # первый зов вообще: базовая линия вместо истории
        return {"file": None, "offset": 0, "baseline_first_run": True}


def save_offset(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = OFFSET_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, OFFSET_FILE)


def seen_has(h):
    try:
        with open(SEEN_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    if json.loads(line).get("hash") == h:
                        return True
                except Exception:  # noqa: BLE001
                    continue
    except OSError:
        pass
    return False


def seen_add(h):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(SEEN_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"hash": h, "ts": int(time.time())}) + "\n")


def incident(row):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(INCIDENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def run():
    path = newest_log()
    if not path:
        print("watch-logs: логов нет — нечего читать")
        return 0
    state = load_offset()
    if state.get("file") != path:
        # ротация: новый файл (старт сервера) — читаем с начала
        incident({"ts": int(time.time()), "class": "log-rotation",
                  "file": os.path.basename(path),
                  "note": "новый файл лога (старт сервера), смещение сброшено"})
        state = {"file": path, "offset": 0}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            f.seek(state.get("offset", 0))
            data = f.read()
            state["offset"] = f.tell()
    except OSError as e:
        print(f"watch-logs: не читается {path}: {e}")
        return 0
    if state.get("baseline_first_run"):
        # первый зов: история лога — НЕ инциденты, базовая линия
        state["baseline_first_run"] = False
        save_offset(state)
        incident({"ts": int(time.time()), "class": "watch-baseline",
                  "file": os.path.basename(path), "lines": len(data.splitlines()),
                  "note": "первый проход — базовая линия, история не в инцидентах"})
        print(f"watch-logs: базовая линия {os.path.basename(path)} "
              f"({len(data.splitlines())} строк истории — пропущены)")
        return 0
    save_offset(state)

    lines = data.splitlines()
    found = 0
    # --- Оси дрейфа канала (мандат sign-rules-to-infra, решение ЦУ 2026-10-30):
    # оси 1 (sent/queued без delivered) и 2 (claims вне реестра) ловим здесь,
    # чтобы дрейф был виден без запуска session-cop. Dedup по seen-хешу.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import drift
        for row in drift.axes((1, 2)):
            h = hashlib.sha256(json.dumps(row, sort_keys=True,
                                          ensure_ascii=False).encode()).hexdigest()[:12]
            if seen_has(h):
                incident({"ts": int(time.time()),
                          "class": "drift:" + str(row.get("class")),
                          "axis": row.get("axis"), "repeat": h,
                          "sid": row.get("sid", ""),
                          "ref": row.get("ref", ""),
                          "message_id": row.get("message_id", "")})
                continue
            seen_add(h)
            incident({"ts": int(time.time()),
                      "class": "drift:" + str(row.get("class")),
                      "axis": row.get("axis"), "hash": h,
                      "sid": row.get("sid", ""),
                      "ref": row.get("ref", ""),
                      "message_id": row.get("message_id", "")})
            found += 1
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"watch-logs: оси дрейфа не отработали ({e!r})\n")
    for i, line in enumerate(lines):
        for cls, needle in PATTERNS:
            if needle in line:
                h = hashlib.sha256(line.encode("utf-8", "replace")).hexdigest()[:12]
                if seen_has(h):
                    incident({"ts": int(time.time()), "class": cls,
                              "file": os.path.basename(path),
                              "repeat": h, "snippet": line[:SNIPPET_MAX]})
                    break
                seen_add(h)
                incident({"ts": int(time.time()), "class": cls,
                          "file": os.path.basename(path), "hash": h,
                          "snippet": line[:SNIPPET_MAX]})
                found += 1
                break
    print(f"watch-logs: {os.path.basename(path)} +{len(lines)} строк, "
          f"новых инцидентов: {found}")
    return 0


def status():
    state = load_offset()
    counts = {}
    try:
        with open(INCIDENTS_FILE, encoding="utf-8") as f:
            n = sum(1 for _ in f)
    except OSError:
        n = 0
    try:
        with open(INCIDENTS_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    counts[json.loads(line).get("class", "?")] = \
                        counts.get(json.loads(line).get("class", "?"), 0) + 1
                except Exception:  # noqa: BLE001
                    continue
    except OSError:
        pass
    print(f"watch-logs: читается {state.get('file')} @offset {state.get('offset')}; "
          f"инцидентов всего {n}; по классам: {counts}")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--status" in args:
        sys.exit(status())
    sys.exit(run())
