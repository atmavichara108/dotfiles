#!/bin/bash
# Delivery-check (B18, read-gate) — детерминированная проверка доставки письма
# по живой БД OpenCode (session_message), без внешнего каталога и без LLM.
#
# Источник истины: ~/.local/share/opencode/opencode.db, таблица session_message,
# type='user' (входящее письмо в сессию). _ack-файлы в /tmp/opencodeREAD —
# устаревший канал (external_directory закрыт), больше не источник.
#
# Usage:
#   delivery-check.sh <sessionID> <hash|substring>
#     hash      — 16..64 hex: сравнивается как префикс sha256(text) письма
#                 (digest из журнала letter.sh — sha256_of тела)
#     substring — ищется как подстрока в тексте входящих писем сессии
#
# Exit: 0 — доставлено (ищемое сообщение найдено)
#       1 — не доставлено
#       2 — ошибка (нет БД/сессии, аргументы)
#
# Только чтение (sqlite mode=ro). Никаких зависимостей кроме python3.
set -euo pipefail

DB="${OPENCODE_DB:-$HOME/.local/share/opencode/opencode.db}"

usage() { echo "Usage: delivery-check.sh <sessionID> <hash|substring>" >&2; exit 2; }

[[ $# -eq 2 ]] || usage
SESSION="$1"; NEEDLE="$2"
[[ -f "${DB}" ]] || { echo "error: db not found: ${DB}" >&2; exit 2; }
[[ "${SESSION}" =~ ^ses_ ]] || { echo "error: bad sessionID: ${SESSION}" >&2; exit 2; }

python3 - "${DB}" "${SESSION}" "${NEEDLE}" <<'PY'
import hashlib, json, re, sqlite3, sys, time

db_path, session, needle = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
except sqlite3.Error as e:
    print(f"error: {e}", file=sys.stderr); sys.exit(2)

rows = con.execute(
    "SELECT id, seq, time_created, data FROM session_message "
    "WHERE session_id=? AND type='user' ORDER BY seq", (session,)
).fetchall()
if not rows and not con.execute(
    "SELECT 1 FROM session_v2 WHERE id=?", (session,)
).fetchone():
    print(f"NOT-DELIVERED: неизвестная сессия {session}", file=sys.stderr)
    sys.exit(2)

hash_mode = re.fullmatch(r"[0-9a-f]{16,64}", needle) is not None
# окно: письма не старше 7 дней (защита от случайных совпадений в прошлом)
cut_ms = int(time.time() * 1000) - 7 * 86400 * 1000
def variants(text):
    # OpenCode ранит входящее письмо кавычками/эскейпом — сравниваем
    # несколько канонизаций, digest letter.sh считается от сырого payload.
    yield text
    s = text.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
    yield s
    yield s.replace('\\"', '"').replace("\\\\", "\\")

for mid, seq, ts, data in rows:
    if ts < cut_ms:
        continue
    try:
        text = (json.loads(data) or {}).get("text") or ""
    except (json.JSONDecodeError, TypeError):
        continue
    if hash_mode:
        if any(hashlib.sha256(v.encode()).hexdigest().startswith(needle)
               for v in variants(text)):
            print(f"DELIVERED: msg={mid} seq={seq} ts={ts} match=hash:{needle}")
            sys.exit(0)
    else:
        if needle in text:
            print(f"DELIVERED: msg={mid} seq={seq} ts={ts} match=substring")
            sys.exit(0)
print(f"NOT-DELIVERED: {needle[:40]} не найдено в {session} (за 7 дней)")
sys.exit(1)
PY
