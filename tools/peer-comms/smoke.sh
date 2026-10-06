#!/bin/bash
# Smoke test for peer-comms handshake.
# Creates a temporary claims file, exercises hello/ack/ping/bye, checks TTL staleness.
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

# --- Test 5: full handshake hello A → hello B → ack B from A → ping B ---
echo "--- Test 5: handshake A↔B → ack refreshes B ---"
"${HELLO}" hello --session A --role builder --model qwen3.7-plus --scope "tools/peer-comms"
"${HELLO}" hello --session B --role verifier --model muse-spark --scope "tools/peer-comms"
"${HELLO}" ack --session B --from A --role builder --model qwen3.7-plus
out="$("${HELLO}" ping B)"
assert "ping B shows active after ack" "active" "${out}"
assert "ping B shows ack from A" "ack from: A" "${out}"
echo ""

# --- Test 6: ack alone keeps session active ---
echo "--- Test 6: ack without bye keeps session active ---"
"${HELLO}" hello --session C --role sysop --model gpt-5.6-luna --scope test
"${HELLO}" ack --session C --from A
out="$("${HELLO}" ping C)"
assert "ping C active after ack" "active" "${out}"
if [[ "${out}" == *"inactive"* ]]; then
  echo "  FAIL: ack should not cause inactive status"
  (( ++fail ))
else
  echo "  PASS: ack does not cause inactive"
  (( ++pass ))
fi
echo ""

# --- Test 7: ack does not override bye ---
echo "--- Test 7: bye after ack → inactive ---"
"${HELLO}" hello --session D --role util-dev --model qwen3.7-plus --scope test
"${HELLO}" ack --session D --from A
"${HELLO}" bye --session D
out="$("${HELLO}" ping D)"
assert "ping D inactive after bye (ack overridden)" "inactive" "${out}"
echo ""

# --- Test 8: list shows registered sessions ---
echo "--- Test 8: list shows registered sessions ---"
"${HELLO}" hello --session X --role builder --model qwen3.7-plus --scope "tools/peer-comms"
out="$("${HELLO}" list)"
assert "list contains header" "SESSION" "${out}"
assert "list shows session X" "X" "${out}"
assert "list shows active status" "active" "${out}"
echo ""

# --- Test 9: find --role returns session ID ---
echo "--- Test 9: find --role builder returns session ID ---"
out="$("${HELLO}" find --role builder)"
assert "find returns session X" "X" "${out}"
echo ""

# --- Test 10: find --role nonexistent → exit 1 ---
echo "--- Test 10: find --role nonexistent → exit 1 ---"
rc=0
out="$("${HELLO}" find --role nonexistent 2>&1)" || rc=$?
if (( rc != 1 )); then
  echo "  FAIL: find should exit 1 for nonexistent role (got exit ${rc})"
  (( ++fail ))
else
  echo "  PASS: find exits 1 for nonexistent role"
  (( ++pass ))
fi
echo ""

# --- Summary ---
echo "=== Results: ${pass} passed, ${fail} failed ==="
if (( fail > 0 )); then
  exit 1
fi
exit 0
