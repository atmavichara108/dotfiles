#!/bin/bash
# Peer letter delivery — единственная канонная точка отправки письма в сессию.
#
# Проблема B15 (model-overwrite): `opencode run -s <id> -m <model>` вызывает
# серверную операцию session.switchModel и ПЕРСИСТЕНТНО переписывает модель
# в самой сессии адресата (opencode.db, session_v2.model). Письмо отправителя
# меняло рабочий профиль получателя.
#
# Guard (вариант 3+2, вердикт Дирижёра 2026-10-07):
#   Guard 1 — по умолчанию письмо уходит БЕЗ `-m` (CLI вызывает switchModel
#             только если модель передана). Модель адресата не меняется.
#   Guard 2 — если `-m` всё же передан и сессия известна в реестре peer-comms
#             (claims.jsonl) с другой моделью — REFUSE (exit 3), не перезапись.
#   Fallback 3 — если `-m` совпадает с текущей моделью адресата из реестра —
#             подаётся как есть (no-op запись).
#
# Read-only: скрипт НЕ пишет в БД, только читает реестр и вызывает opencode run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAIMS_FILE="${CLAIMS_FILE:-${SCRIPT_DIR}/claims.jsonl}"

fail() { echo "Error: $*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage:
  letter.sh --to <sessionID> [--model <provider/model>] [--title <t>] --file <path>
  letter.sh --to <sessionID> [--model <provider/model>] --text "<message>"

Guard (B15, model-overwrite):
  без --model    -> письмо уходит без switchModel; модель адресата не меняется
  с --model      -> REFUSE (exit 3), если модель отличается от зарегистрированной
  --force-model  -> явный обход guard (печатает WARN про перезапись профиля)
EOF
}

resolve_registered_model() {
  local session="${1:?}"
  [[ -f "${CLAIMS_FILE}" ]] || return 0
  jq -R -c --arg s "${session}" \
    'fromjson? // empty | select(.session == $s and (.model // "") != "")' \
    "${CLAIMS_FILE}" 2>/dev/null | tail -n 1 | jq -r '.model // empty'
}

main() {
  local to="" model="" title="" text="" file="" force=false
  while (( $# > 0 )); do
    case "$1" in
      --to)          to="${2:?--to requires a value}"; shift 2 ;;
      --model)       model="${2:?--model requires a value}"; shift 2 ;;
      --title)       title="${2:?--title requires a value}"; shift 2 ;;
      --text)        text="${2:?--text requires a value}"; shift 2 ;;
      --file)        file="${2:?--file requires a value}"; shift 2 ;;
      --force-model) force=true; shift ;;
      -h|--help|help) usage; return 0 ;;
      *) fail "Unknown option: $1" ;;
    esac
  done

  [[ -n "${to}" ]] || fail "--to is required"
  [[ -n "${text}" || -n "${file}" ]] || fail "--text or --file is required"

  # --file: текст письма читается из файла (канон против shell-quote багов)
  local payload
  if [[ -n "${file}" ]]; then
    [[ -f "${file}" ]] || fail "--file not found: ${file}"
    payload="$(cat "${file}")"
  else
    payload="${text}"
  fi

  local args=("run" "-s" "${to}")
  [[ -n "${title}" ]] && args+=("--title" "${title}")

  if [[ -n "${model}" ]]; then
    local registered
    registered="$(resolve_registered_model "${to}" || true)"
    if [[ "${force}" != true ]]; then
      if [[ -n "${registered}" && "${registered}" != "${model}" ]]; then
        echo "REFUSE: recipient ${to} is registered with model '${registered}', letter carries '${model}'." >&2
        echo "REFUSE: sending would overwrite the recipient profile (B15). Use --force-model to override." >&2
        exit 3
      fi
      if [[ -z "${registered}" ]]; then
        echo "REFUSE: recipient ${to} unknown in registry — cannot verify model '${model}'." >&2
        echo "REFUSE: register the session (hello.sh hello) or send without --model." >&2
        exit 3
      fi
    else
      echo "WARN: --force-model overwrites recipient profile (${registered:-unknown} -> ${model})" >&2
    fi
    args+=("-m" "${model}")
  fi

  args+=("${payload}")
  exec opencode "${args[@]}"
}

main "$@"