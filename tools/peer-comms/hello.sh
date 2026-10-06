#!/bin/bash
# Peer session handshake — register, ping, and deregister parallel sessions.
# Append-only JSONL log at tools/peer-comms/claims.jsonl.
# Semantics: ping is a read-only status query; TTL counts from the last hello.
# A session stays active only while re-helloing within TTL_MINUTES.
#
# CANON: sessionID is resolved ONLY via `find --role <role>` (claims.jsonl registry).
# Guessing by freshness or `opencode session list` is FORBIDDEN.
# Sending a message to your own session is NOT detected by the transport.
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

# _aggregate_sessions: internal helper — jq expression that groups claims.jsonl
# by session, takes the last record per session, computes status, and returns
# a JSON array sorted active-first.
# Reads from stdin (piped claims content) to avoid re-reading the file.
_aggregate_sessions_jq() {
  local now="${1:?}" ttl_sec="${2:?}"
  jq -s --argjson now "${now}" --argjson ttl "${ttl_sec}" '
    group_by(.session) |
    map(
      last |
      ($now - .ts) as $raw_age |
      (if $raw_age < 0 then 0 else $raw_age end) as $age |
      (if .op == "bye" then "inactive"
       elif $age > $ttl then "stale"
       else "active"
       end) as $status |
      {
        session: .session,
        role:    (.role // ""),
        model:   (.model // ""),
        scope:   (.scope // ""),
        age_sec: $age,
        status:  $status
      }
    ) |
    sort_by(
      if   .status == "active"  then 0
      elif .status == "stale"   then 1
      else 2
      end
    )
  '
}

cmd_list() {
  local json_output=false
  while (( $# > 0 )); do
    case "$1" in
      --json) json_output=true; shift ;;
      *)      die "Unknown option: $1" ;;
    esac
  done

  ensure_claims_file

  local now ttl_sec
  now="$(now_epoch)"
  ttl_sec=$(( TTL_MINUTES * 60 ))

  local aggregated
  aggregated="$(_aggregate_sessions_jq "${now}" "${ttl_sec}" < "${CLAIMS_FILE}")"

  if [[ "${json_output}" == true ]]; then
    echo "${aggregated}" | jq .
    return
  fi

  printf "%-40s %-20s %-25s %-25s %-10s %-10s\n" \
    "SESSION" "ROLE" "MODEL" "SCOPE" "AGE" "STATUS"
  printf "%-40s %-20s %-25s %-25s %-10s %-10s\n" \
    "-------" "----" "-----" "-----" "---" "------"

  # age_human is computed in jq to avoid bash IFS whitespace collapsing empty fields.
  # awk -F'\t' (unlike bash read) preserves empty TSV fields correctly.
  echo "${aggregated}" | jq -r '
    def age_h:
      if   . < 60   then "\(.)s"
      elif . < 3600 then "\(. / 60 | floor)m"
      else "\(. / 3600 | floor)h\((. % 3600) / 60 | floor)m"
      end;
    .[] | [.session, .role, .model, .scope, (.age_sec | age_h), .status] | @tsv
  ' | awk -F'\t' '{printf "%-40s %-20s %-25s %-25s %-10s %-10s\n", $1, $2, $3, $4, $5, $6}'
}

cmd_find() {
  local role="" json_output=false
  while (( $# > 0 )); do
    case "$1" in
      --role) role="${2:?--role requires a value}"; shift 2 ;;
      --json) json_output=true; shift ;;
      *)      die "Unknown option: $1" ;;
    esac
  done

  [[ -n "${role}" ]] || die "--role is required"
  ensure_claims_file

  local now ttl_sec
  now="$(now_epoch)"
  ttl_sec=$(( TTL_MINUTES * 60 ))

  local aggregated
  aggregated="$(_aggregate_sessions_jq "${now}" "${ttl_sec}" < "${CLAIMS_FILE}")"

  # Filter to matching role + active status, extract sessionIDs
  local sessions
  sessions="$(echo "${aggregated}" | jq --arg role "${role}" '
    [.[] | select(.role == $role and .status == "active") | .session]
  ')"

  local count
  count="$(echo "${sessions}" | jq 'length')"

  if (( count == 0 )); then
    echo "No active sessions found with role '${role}'" >&2
    exit 1
  fi

  if [[ "${json_output}" == true ]]; then
    echo "${sessions}" | jq .
  else
    echo "${sessions}" | jq -r '.[]'
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
  hello.sh list [--json]
  hello.sh find --role <role> [--json]
EOF
}

main() {
  command -v jq >/dev/null 2>&1 || die "jq is required but not installed"
  local cmd="${1:-}"
  shift || die "Command required (hello|ack|ping|bye|list|find)"

  case "${cmd}" in
    hello) cmd_hello "$@" ;;
    ack)   cmd_ack "$@" ;;
    ping)  cmd_ping "$@" ;;
    bye)   cmd_bye "$@" ;;
    list)  cmd_list "$@" ;;
    find)  cmd_find "$@" ;;
    -h|--help|help) usage ;;
    *) die "Unknown command: ${cmd}" ;;
  esac
}

main "$@"
