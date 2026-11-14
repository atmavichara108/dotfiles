#!/bin/bash
# tests-claim-failclosed — приёмка У-1 операции «Гомеостаз» (fail-closed claim).
#
#   1) claim от sid вне peer-registry — ОТКАЗ, ненулевой rc;
#   2) claim от зарегистрированного sid — проходит;
#   3) чужая активная заявка блокирует ту же ветку;
#   4) просроченный claim не блокирует (истекает сам, ручная чистка не нужна).
#
# Изоляция: временный CLAIMS_FILE и фикстурный PEER_REGISTRY.
# Запуск: bash tools/peer-comms/tests-claim-failclosed.sh def
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELLO="${SCRIPT_DIR}/hello.sh"

WORK_DIR="$(mktemp -d /tmp/opencode/peer-claim-test.XXXXXX)"
trap 'rm -rf "${WORK_DIR}"' EXIT

export CLAIMS_FILE="${WORK_DIR}/claims.jsonl"
: > "${CLAIMS_FILE}"

export PEER_REGISTRY="${WORK_DIR}/registry.md"
printf '%s\n' \
  '| Ведомство | Сессия | Агент | Каталог | Зона |' \
  '|---|---|---|---|---|' \
  '| Своя | ses_KNOWNOWNER01 | builder | ~/dotfiles | тест |' \
  '| Чужая | ses_OTHEROWNER01 | builder | ~/dotfiles | тест |' \
  > "${PEER_REGISTRY}"

pass=0
fail=0

ok()  { echo "  PASS: $1"; (( ++pass )); }
bad() { echo "  FAIL: $1"; echo "        $2"; (( ++fail )); }

echo "=== У-1: fail-closed claim ==="

set +e
out="$("${HELLO}" claim --session ses_GHOSTNOTREG01 --branch task/ghost --scope тест 2>&1)"
rc=$?
set -e
if (( rc != 0 )) && [[ "${out}" == *refused* ]]; then
  ok "claim вне реестра отказан (rc=${rc})"
else
  bad "claim вне реестра отказан" "rc=${rc}, out=${out}"
fi

if grep -q "ses_GHOSTNOTREG01" "${CLAIMS_FILE}"; then
  bad "призрачный sid не попал в журнал" "запись найдена"
else
  ok "призрачный sid не попал в журнал"
fi

out="$("${HELLO}" claim --session ses_KNOWNOWNER01 --branch task/known --scope тест 2>&1)"
if [[ "${out}" == *"task/known"* ]]; then
  ok "claim известного sid принят"
else
  bad "claim известного sid принят" "${out}"
fi

set +e
out="$("${HELLO}" claim --session ses_OTHEROWNER01 --branch task/known --scope тест 2>&1)"
rc=$?
set -e
if (( rc != 0 )) && [[ "${out}" == *"уже заявлена"* ]]; then
  ok "чужая активная заявка блокирует ветку (rc=${rc})"
else
  bad "чужая активная заявка блокирует ветку" "rc=${rc}, out=${out}"
fi

python3 - "${CLAIMS_FILE}" <<'PY'
import json, sys, time
p = sys.argv[1]
rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
rows.append({"op": "claim", "session": "ses_OTHEROWNER01",
             "branch": "task/stale", "scope": "t",
             "ts": int(time.time()) - 7200, "ttl_minutes": 1})
with open(p, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
PY

set +e
out="$("${HELLO}" claim --session ses_KNOWNOWNER01 --branch task/stale --scope тест 2>&1)"
rc=$?
set -e
if (( rc == 0 )) && [[ "${out}" == *"task/stale"* ]]; then
  ok "просроченный claim не блокирует (истёк сам)"
else
  bad "просроченный claim не блокирует" "rc=${rc}, out=${out}"
fi

echo "=== ${pass} pass, ${fail} fail ==="
(( fail == 0 )) || exit 1
exit 0
