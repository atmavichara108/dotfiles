#!/bin/bash
# Peer session handshake — register, ping, and deregister parallel sessions.
# Append-only JSONL log at tools/peer-comms/claims.jsonl.
# Semantics: ping is a read-only status query; TTL counts from the last hello.
# A session stays active only while re-helloing within TTL_MINUTES.
set -euo pipefail

# --- Constants ---
TTL_MINUTES=30
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAIMS_FILE="${CLAIMS_FILE:-${SCRIPT_DIR}/claims.jsonl}"

# --- Helpers ---
die() { echo "Error: $*" >&2; exit 1; }

now_epoch() { date +%s; }

iso_timestamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

age_human() {
  local seconds="${1:?}"
  if (( seconds < 60 )); then
    echo "${seconds}s"
  elif (( seconds < 3600 )); then
    echo "$(( seconds / 60 ))m"
  else
    echo "$(( seconds / 3600 ))h$(( (seconds % 3600) / 60 ))m"
  fi
}

ensure_claims_file() {
  if [[ ! -f "${CLAIMS_FILE}" ]]; then
    touch "${CLAIMS_FILE}"
  fi
}

# --- Commands ---

cmd_hello() {
  local session="" role="" model="" scope=""

  while (( $# > 0 )); do
    case "$1" in
      --session)  session="${2:?--session requires a value}"; shift 2 ;;
      --role)     role="${2:?--role requires a value}"; shift 2 ;;
      --model)    model="${2:?--model requires a value}"; shift 2 ;;
      --scope)    scope="${2:?--scope requires a value}"; shift 2 ;;
      *) die "Unknown option: $1" ;;
    esac
  done

  [[ -n "${session}" ]] || die "--session is required"
  [[ -n "${role}" ]]    || die "--role is required"
  [[ -n "${model}" ]]   || die "--model is required"
  [[ -n "${scope}" ]]   || die "--scope is required"

  ensure_claims_file

  local ts
  ts="$(now_epoch)"

  jq -c -n \
    --arg op "hello" \
    --arg session "${session}" \
    --arg role "${role}" \
    --arg model "${model}" \
    --arg scope "${scope}" \
    --argjson ts "${ts}" \
    --argjson ttl "${TTL_MINUTES}" \
    '{op: $op, session: $session, role: $role, model: $model, scope: $scope, ts: $ts, ttl_minutes: $ttl}' \
    >> "${CLAIMS_FILE}"

  echo "Registered session '${session}' (${role}, ${model}) — scope: ${scope}"
}

cmd_ack() {
  local session="" from="" role="" model="" scope=""

  while (( $# > 0 )); do
    case "$1" in
      --session)  session="${2:?--session requires a value}"; shift 2 ;;
      --from)     from="${2:?--from requires a value}"; shift 2 ;;
      --role)     role="${2:?--role requires a value}"; shift 2 ;;
      --model)    model="${2:?--model requires a value}"; shift 2 ;;
      --scope)    scope="${2:?--scope requires a value}"; shift 2 ;;
      *) die "Unknown option: $1" ;;
    esac
  done

  [[ -n "${session}" ]] || die "--session is required (recipient)"
  [[ -n "${from}" ]]    || die "--from is required (sender)"

  ensure_claims_file

  local ts
  ts="$(now_epoch)"

  jq -c -n \
    --arg op "ack" \
    --arg session "${session}" \
    --arg from "${from}" \
    --arg role "${role}" \
    --arg model "${model}" \
    --arg scope "${scope}" \
    --argjson ts "${ts}" \
    '{op: $op, session: $session, from: $from, ts: $ts}
     + (if $role != "" then {role: $role} else {} end)
     + (if $model != "" then {model: $model} else {} end)
     + (if $scope != "" then {scope: $scope} else {} end)' \
    >> "${CLAIMS_FILE}"

  echo "Acknowledged session '${session}' from '${from}'"
}

cmd_bye() {
  local session=""

  while (( $# > 0 )); do
    case "$1" in
      --session) session="${2:?--session requires a value}"; shift 2 ;;
      *) die "Unknown option: $1" ;;
    esac
  done

  [[ -n "${session}" ]] || die "--session is required"
  ensure_claims_file

  local ts
  ts="$(now_epoch)"

  jq -c -n \
    --arg op "bye" \
    --arg session "${session}" \
    --argjson ts "${ts}" \
    '{op: $op, session: $session, ts: $ts}' \
    >> "${CLAIMS_FILE}"

  echo "Deregistered session '${session}'"
}

cmd_ping() {
  local session="${1:?Usage: ping <sessionId>}"
  shift

  local json_output=false
  while (( $# > 0 )); do
    case "$1" in
      --json) json_output=true; shift ;;
      *) die "Unknown option: $1" ;;
    esac
  done

  ensure_claims_file

  local now
  now="$(now_epoch)"

  # Find the last valid record for this session (skip corrupted lines)
  local last_record
  last_record="$(jq -R -c --arg s "${session}" 'fromjson? // empty | select(.session == $s)' "${CLAIMS_FILE}" 2>/dev/null | tail -n 1 || true)"

  if [[ -z "${last_record}" ]]; then
    if [[ "${json_output}" == true ]]; then
      jq -n --arg session "${session}" '{session: $session, status: "unknown", message: "no records found"}'
    else
      echo "Session '${session}': unknown (no records)"
    fi
    return 0
  fi

  local op ts role model scope from
  op="$(echo "${last_record}" | jq -r '.op')"
  ts="$(echo "${last_record}" | jq -r '.ts')"
  role="$(echo "${last_record}" | jq -r '.role // empty')"
  model="$(echo "${last_record}" | jq -r '.model // empty')"
  scope="$(echo "${last_record}" | jq -r '.scope // empty')"
  from="$(echo "${last_record}" | jq -r '.from // empty')"

  local age=$(( now - ts ))
  (( age < 0 )) && age=0 # clock skew: future ts clamps to zero
  local age_str
  age_str="$(age_human "${age}")"

  # op == "bye" is the only terminal state; hello and ack both mean active.
  local status
  if [[ "${op}" == "bye" ]]; then
    status="inactive"
  elif (( age > TTL_MINUTES * 60 )); then
    status="stale"
  else
    status="active"
  fi

  if [[ "${json_output}" == true ]]; then
    jq -n \
      --arg session "${session}" \
      --arg op "${op}" \
      --arg role "${role}" \
      --arg model "${model}" \
      --arg scope "${scope}" \
      --arg from "${from}" \
      --arg age "${age_str}" \
      --arg status "${status}" \
      '{session: $session, op: $op, role: $role, model: $model, scope: $scope, from: $from, age: $age, status: $status}'
  else
    printf "Session %-20s role=%-16s model=%-20s scope=%-20s age=%-8s status=%s\n" \
      "${session}" "${role}" "${model}" "${scope}" "${age_str}" "${status}"
    if [[ -n "${from}" ]]; then
      echo "  ack from: ${from}"
    fi
  fi
}

# --- Main ---

usage() {
  cat <<'EOF'
Usage:
  hello.sh hello --session <id> --role <role> --model <model> --scope <scope>
  hello.sh ack  --session <recipient> --from <sender> [--role <role>] [--model <model>] [--scope <scope>]
  hello.sh ping <sessionId> [--json]
  hello.sh bye  --session <id>
EOF
}

main() {
  command -v jq >/dev/null 2>&1 || die "jq is required but not installed"
  local cmd="${1:-}"
  shift || die "Command required (hello|ack|ping|bye)"

  case "${cmd}" in
    hello) cmd_hello "$@" ;;
    ack)   cmd_ack "$@" ;;
    ping)  cmd_ping "$@" ;;
    bye)   cmd_bye "$@" ;;
    -h|--help|help) usage ;;
    *) die "Unknown command: ${cmd}" ;;
  esac
}

main "$@"
