#!/bin/bash
# Smoke test for peer-comms handshake.
# Creates a temporary claims file, exercises hello/ping/bye, checks TTL staleness.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELLO="${SCRIPT_DIR}/hello.sh"

WORK_DIR="$(mktemp -d /tmp/opencode/peer-comms-smoke.XXXXXX)"
trap 'rm -rf "${WORK_DIR}"' EXIT

export CLAIMS_FILE="${WORK_DIR}/claims.jsonl"
touch "${CLAIMS_FILE}"

pass=0
fail=0

assert() {
  local label="$1" expected="$2" actual="$3"
  if [[ "${actual}" == *"${expected}"* ]]; then
    echo "  PASS: ${label}"
    (( ++pass ))
  else
    echo "  FAIL: ${label}"
    echo "    expected substring: ${expected}"
    echo "    actual:             ${actual}"
    (( ++fail ))
  fi
}

echo "=== Peer-comms smoke test ==="
echo ""

# --- Test 1: hello + ping shows active ---
echo "--- Test 1: hello A → ping A → active ---"
"${HELLO}" hello --session A --role builder --model qwen3.7-plus --scope "tools/peer-comms"
out="$("${HELLO}" ping A)"
assert "ping shows session A" "Session A" "${out}"
assert "ping shows active" "active" "${out}"
echo ""

# --- Test 2: bye + ping shows inactive ---
echo "--- Test 2: bye A → ping A → inactive ---"
"${HELLO}" bye --session A
out="$("${HELLO}" ping A)"
assert "ping shows inactive after bye" "inactive" "${out}"
echo ""

# --- Test 3: stale TTL ---
echo "--- Test 3: stale session (ts > TTL) → stale ---"
"${HELLO}" hello --session B --role verifier --model muse-spark --scope test
# Rewrite ts to 2 hours ago (well beyond 30-min TTL)
old_ts=$(( $(date +%s) - 7200 ))
# Replace ts for session B entries with old_ts
jq -c --argjson old_ts "${old_ts}" \
  'if .session == "B" and .op == "hello" then .ts = $old_ts else . end' \
  "${CLAIMS_FILE}" > "${WORK_DIR}/claims_tmp.jsonl"
mv "${WORK_DIR}/claims_tmp.jsonl" "${CLAIMS_FILE}"
out="$("${HELLO}" ping B)"
assert "ping shows stale" "stale" "${out}"
echo ""

# --- Test 4: unknown session ---
echo "--- Test 4: unknown session → unknown ---"
out="$("${HELLO}" ping ZZZ)"
assert "ping unknown shows unknown" "unknown" "${out}"
echo ""

# --- Summary ---
echo "=== Results: ${pass} passed, ${fail} failed ==="
if (( fail > 0 )); then
  exit 1
fi
exit 0
