#!/bin/bash
# Head-guard (B22) — защита от перехвата HEAD в общем checkout (dotfiles).
#
# Симптом инцидента 2026-10-07: параллельная сессия переключила общий
# worktree посреди чужой работы — коммиты легли на чужую task-ветку.
# Pre-commit различал main vs task/*, но не ВЛАДЕЛЬЦА task-ветки.
#
# Источник истины: claims.jsonl (плоскость scope, не доставка). Записи
# владельца создаёт `hello.sh claim --session <id> --branch task/...`
# (op=claim), снимает `hello.sh claim-release` (op=release).
#
# Режим (выбор sysop, обоснование в handoff): SOFT-BLOCK — блокируем только
# при конкретных уликах: на task/*-ветке есть СВЕЖИЙ claim другого сессионного
# id. Все неопознанные случаи — тихий pass с WARN в журнал (не блокируем жизнь):
#   - не task/*-ветка                → exit 0, молча
#   - нет ни одного claim на ветку   → exit 0, молча (легаси-ветки)
#   - последний op=release           → exit 0, молча (владелец отпустил)
#   - claim протух (возраст > ttl)   → WARN в журнал, exit 0
#   - текущая сессия не опознать     → WARN в журнал, exit 0
#   - владелец == текущая сессия     → exit 0 (своя ветка)
#   - чужой свежий claim             → exit 1 (BLOCK) + журнал
# Обход в pre-commit: HEAD_GUARD_OK=1 (осознанно, как MIXED_OK).
#
# Exit: 0 разрешить | 1 чужая ветка | 2 ошибка аргументов.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAIMS_FILE="${HEAD_GUARD_CLAIMS:-${SCRIPT_DIR}/../peer-comms/claims.jsonl}"
LOG_FILE="${HEAD_GUARD_LOG:-$HOME/.local/state/opencode/head-guard.log}"
DEFAULT_TTL_MIN=240  # ветку держат часами; 30-мин TTL хello тут не годится

journal() {
  # metadata-only, append-only
  mkdir -p "$(dirname "${LOG_FILE}")" 2>/dev/null || return 0
  printf '%s\n' "$*" >> "${LOG_FILE}" 2>/dev/null || true
}

usage() { echo "Usage: head-guard.sh check [--branch <b>] [--session <id>]" >&2; exit 2; }

[[ "${1:-check}" == "check" ]] || usage
shift || true
branch=""; session="${OPENCODE_SESSION_ID:-}"
while (( $# > 0 )); do
  case "$1" in
    --branch)  [[ $# -ge 2 ]] || usage; branch="$2"; shift 2 ;;
    --session) [[ $# -ge 2 ]] || usage; session="$2"; shift 2 ;;
    *) usage ;;
  esac
done
[[ -n "${branch}" ]] || branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"

case "${branch}" in
  task/*) : ;;
  *) exit 0 ;;
esac
[[ -f "${CLAIMS_FILE}" ]] || exit 0

# Последняя владельческая запись по ветке (append-only: tail = последнее).
last="$(jq -R -c --arg b "${branch}" \
  'fromjson? // empty | select(.branch == $b and (.op == "claim" or .op == "release"))' \
  "${CLAIMS_FILE}" 2>/dev/null | tail -n 1 || true)"
[[ -n "${last}" ]] || exit 0

op="$(jq -r '.op' <<<"${last}")"
[[ "${op}" == "release" ]] && exit 0

owner="$(jq -r '.session // "?"' <<<"${last}")"
scope="$(jq -r '.scope // ""' <<<"${last}")"
ts="$(jq -r '.ts // 0' <<<"${last}")"
ttl_min="$(jq -r --argjson d "${DEFAULT_TTL_MIN}" '.ttl_minutes // $d' <<<"${last}")"
now="$(date +%s)"
age=$(( now - ts )); (( age < 0 )) && age=0

if (( age > ttl_min * 60 )); then
  journal "$(jq -cn --arg ev "stale-claim" --arg b "${branch}" --arg o "${owner}" --argjson age "${age}" '{ts:(now|floor),event:$ev,branch:$b,owner:$o,age_sec:$age}')"
  exit 0
fi

if [[ -z "${session}" ]]; then
  # исполнитель не опознать — не блокируем жизнь, только след в журнал
  echo "head-guard: WARN — ветка '${branch}' заявлена за ${owner}, а текущая сессия не опознана (OPENCODE_SESSION_ID пуст). Commit разрешён; журнал: ${LOG_FILE}" >&2
  journal "$(jq -cn --arg ev "unknown-executor" --arg b "${branch}" --arg o "${owner}" '{ts:(now|floor),event:$ev,branch:$b,owner:$o}')"
  exit 0
fi

if [[ "${session}" == "${owner}" ]]; then
  exit 0
fi

msg="head-guard: BLOCK — '${branch}' заявлена за сессией ${owner}${scope:+ (scope: ${scope})}, возраст $(( age / 60 )) мин. Ты: ${session:0:20}… Это чужая task-ветка: переключение общего worktree чужой сессией (B22). Вернись на свою ветку или договорись с владельцем. Обход: HEAD_GUARD_OK=1 git commit ..."
echo "${msg}" >&2
journal "$(jq -cn --arg b "${branch}" --arg o "${owner}" --arg s "${session}" --argjson age "${age}" '{ts:(now|floor),event:"block",branch:$b,owner:$o,executor:$s,age_sec:$age}')"
exit 1
