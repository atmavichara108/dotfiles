#!/bin/bash
# Тесты фикса peer-mail-loss-20261024: честная доставка + входные гейты.
# Всё гоняется ТОЛЬКО в изолированном PEER_MAIL_DIR (tmp) — боевой журнал
# ~/.local/state/opencode/mail не трогается. Доставка — на изолированных
# фейковых шимах opencode (run -> exit 0|7, api -> настоящий opencode):
# ни одно тестовое письмо не инжектится в живую сессию.
# Регресс: --model остаётся REFUSE 3.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LETTER="${SCRIPT_DIR}/letter.sh"
VALIDATOR="${SCRIPT_DIR}/validate-registry.py"
REAL_OPENCODE="$(command -v opencode || true)"

TEST_MAIL="$(mktemp -d /tmp/opencode/peer-mail-test.XXXXXX)"
trap 'rm -rf "${TEST_MAIL}"' EXIT
export PEER_MAIL_DIR="${TEST_MAIL}/mail"

pass=0; fail=0
ok()  { echo "  PASS: $1"; pass=$((pass+1)); }
bad() { echo "  FAIL: $1"; fail=$((fail+1)); }

journal_has() { # journal_has <jsonl-фрагмент> — факт события в журнале
  [[ -f "${PEER_MAIL_DIR}/receipts-out.jsonl" ]] \
    && grep -qF "$1" "${PEER_MAIL_DIR}/receipts-out.jsonl"
}

# --- Фикстуры ----------------------------------------------------------------
# Шим opencode: api -> настоящий бинарник (кроме фикстурных id — для них
# шим отвечает «живой сессией», чтобы гейты/busy работали без боевой БД);
# run -> детерминированный код возврата (изолированная «доставка»).
make_shim() { # make_shim <dir> <run-rc>
  local dir="$1" rc="$2"
  mkdir -p "${dir}"
  cat > "${dir}/opencode" <<EOF
#!/bin/bash
if [[ "\${1:-}" == "api" && "\${3:-}" == /api/session/ses_fixmail* ]]; then
  printf '{"data":{"id":"%s","time":{"idle":1,"updated":0}}}\n' "\${3##*/}"
  exit 0
fi
if [[ "\${1:-}" == "api" ]]; then exec "${REAL_OPENCODE}" "\$@"; fi
exit ${rc}
EOF
  chmod +x "${dir}/opencode"
}

# Фикстура реестра: живой агент для тестового адресата (мёртвая сессия).
REG_FIXTURE="${TEST_MAIL}/registry-live.md"
DEAD_TARGET="ses_fixmaildead0000000000000000"
HAPPY_TARGET="ses_fixmailhappy000000000000000"
cat > "${REG_FIXTURE}" <<EOF
| Ведомство | Session ID | Агент | Каталог | Роль |
|---|---|---|---|---|
| Пустой агент | ses_fixmailnone00000000000000 | — (агент не назначен) | /tmp | смотритель |
| Тире | ses_fixmaildash00000000000000 | — | /tmp | смотритель |
| Живой агент | ses_fixmaillive00000000000000 | **Dr.Who** | /tmp | лаборатория |
| Мёртвая цель | ${DEAD_TARGET} | librarian | /tmp | тест отказов |
| Счастливая цель | ${HAPPY_TARGET} | librarian | /tmp | тест доставки |
EOF

# Парсер тестируем напрямую: вырезаем функцию из letter.sh в subshell.
run_registry_agent() {
  local sid="$1"
  REGISTRY_FILE="${REG_FIXTURE}" bash -c '
    REGISTRY_FILE="${REGISTRY_FILE:?}"
    fail() { echo "Error: $*" >&2; exit 1; }
    '"$(sed -n '/^registry_agent()/,/^}/p' "${LETTER}")"'
    registry_agent "'"${sid}"'"
  ' 2>/dev/null
}

# Ручная постановка в очередь (как enqueue_pending, минус гейты) — чтобы
# протестировать механику drain: re-queue -> dead-letter.
enqueue_fixture() { # enqueue_fixture <mid> <to> <body>
  local mid="$1" to="$2" body="$3"
  local pp="${PEER_MAIL_DIR}/pending/${mid}.txt"
  mkdir -p "${PEER_MAIL_DIR}/pending"
  printf '%s' "${body}" > "${pp}"
  jq -c -n \
    --arg mid "${mid}" --arg digest "$(printf '%s' "${body}" | sha256sum | cut -d' ' -f1)" \
    --arg to "${to}" --arg from "ses_fixmailsender00000000000" \
    --arg pp "${pp}" --argjson ts "$(date +%s)" \
    '{op:"queued", message_id:$mid, digest:$digest, to:$to, from:$from,
      scope:"fixture", title:"тест", payload_path:$pp, queued_ts:$ts, attempts:0}' \
    >> "${PEER_MAIL_DIR}/pending.jsonl"
}

echo "=== Тесты фикса канала писем (peer-mail-loss-20261024) ==="
echo "    изолированный PEER_MAIL_DIR: ${PEER_MAIL_DIR}"
echo ""

# --- (a) registry_agent: «— (агент не назначен)» -> пусто -------------------
echo "--- (a) парсер реестра ---"
v="$(run_registry_agent ses_fixmailnone00000000000000)"
if [[ -z "${v}" ]]; then ok "(a1) «— (агент не назначен)» -> пусто"; else bad "(a1) получил «${v}»"; fi
v="$(run_registry_agent ses_fixmaildash00000000000000)"
if [[ -z "${v}" ]]; then ok "(a2) «—» -> пусто"; else bad "(a2) получил «${v}»"; fi
v="$(run_registry_agent ses_fixmaillive00000000000000)"
if [[ "${v}" == "dr-who" ]]; then ok "(a3) «**Dr.Who**» -> dr-who"; else bad "(a3) получил «${v}»"; fi
echo ""

# --- (b) механика отказов: failed -> re-queue -> dead-letter + bounce --------
echo "--- (b) LETTER_MAX_ATTEMPTS=2, доставка отказывает (шим exit 7) ---"
make_shim "${TEST_MAIL}/bin-fail" 7
MID_B="fixmaildead000000-20261024-ses_fixmailsender"
enqueue_fixture "${MID_B}" "${DEAD_TARGET}" "тестовое письмо b: проверка dead-letter"

DRAIN_ENV=(env PEER_MAIL_DIR="${PEER_MAIL_DIR}" PEER_REGISTRY="${REG_FIXTURE}" \
  LETTER_MAX_ATTEMPTS=2 LETTER_QUEUE_TTL=0 LETTER_DRAIN_BUDGET=20 LETTER_DRAIN_TIMEOUT=10 \
  PATH="${TEST_MAIL}/bin-fail:${PATH}")
"${DRAIN_ENV[@]}" "${LETTER}" --drain >/dev/null 2>&1

if journal_has '"event":"failed"'; then ok "(b1) прогон 1: событие failed в журнале"; else bad "(b1) нет failed"; fi
b_att="$(jq -r '.attempts // 0' "${PEER_MAIL_DIR}/pending.jsonl" 2>/dev/null | head -1)"
if [[ "${b_att}" == "1" ]]; then ok "(b2) прогон 1: запись в очереди с attempts=1"; else bad "(b2) attempts=${b_att}, ждали 1"; fi

"${DRAIN_ENV[@]}" "${LETTER}" --drain >/dev/null 2>&1

if journal_has '"event":"dead-letter"'; then ok "(b3) прогон 2: событие dead-letter"; else bad "(b3) нет dead-letter"; fi
bcount=0
[[ -d "${PEER_MAIL_DIR}/pending/bounce" ]] \
  && bcount="$(find "${PEER_MAIL_DIR}/pending/bounce" -name '*.txt' 2>/dev/null | wc -l)"
if (( bcount >= 1 )); then ok "(b4) bounce-файл создан"; else bad "(b4) bounce не создан"; fi
if [[ -d "${PEER_MAIL_DIR}/pending/dead" ]] \
   && (( $(find "${PEER_MAIL_DIR}/pending/dead" -name '*.txt' 2>/dev/null | wc -l) >= 1 )); then
  ok "(b5) payload в pending/dead/"
else
  bad "(b5) payload не в pending/dead/"
fi
left=0
[[ -s "${PEER_MAIL_DIR}/pending.jsonl" ]] && left="$(grep -c . "${PEER_MAIL_DIR}/pending.jsonl")"
if (( left == 0 )); then ok "(b6) запись ушла из очереди после исчерпания попыток"; else bad "(b6) в очереди осталось ${left}"; fi
if (( bcount >= 1 )) && ! grep -q "проверка dead-letter" "${PEER_MAIL_DIR}/pending/bounce/"*.txt 2>/dev/null; then
  ok "(b7) в bounce только метаданные, тела письма нет"
else
  bad "(b7) bounce пуст или содержит тело письма"
fi
echo ""

# --- (c) счастливый путь: delivered ------------------------------------------
echo "--- (c) счастливый путь: delivered (шим exit 0) ---"
make_shim "${TEST_MAIL}/bin-ok" 0
printf 'ТЕСТ канала (c): счастливый путь, фикс peer-mail-loss' > "${TEST_MAIL}/body-c.txt"
env PEER_MAIL_DIR="${PEER_MAIL_DIR}" PEER_REGISTRY="${REG_FIXTURE}" \
  LETTER_QUEUE_TTL=0 LETTER_DRAIN_BUDGET=20 LETTER_DRAIN_TIMEOUT=10 \
  PATH="${TEST_MAIL}/bin-ok:${PATH}" \
  "${LETTER}" --to "${HAPPY_TARGET}" --from ses_fixmailsender00000000000 \
  --title "ТЕСТ (c)" --file "${TEST_MAIL}/body-c.txt" >/dev/null 2>&1
# Дожим: если адресат числился занятым, письмо в очереди — drain с TTL=0
# доставляет безусловно.
env PEER_MAIL_DIR="${PEER_MAIL_DIR}" PEER_REGISTRY="${REG_FIXTURE}" \
  LETTER_MAX_ATTEMPTS=3 LETTER_QUEUE_TTL=0 LETTER_DRAIN_BUDGET=20 LETTER_DRAIN_TIMEOUT=10 \
  PATH="${TEST_MAIL}/bin-ok:${PATH}" \
  "${LETTER}" --drain >/dev/null 2>&1
if journal_has '"event":"delivered"'; then ok "(c1) событие delivered в журнале"; else bad "(c1) нет delivered"; fi
echo ""

# --- (d) регресс: --model -> REFUSE exit 3 -----------------------------------
echo "--- (d) --model -> REFUSE 3 ---"
out="$("${LETTER}" --to "${HAPPY_TARGET}" --model quick 2>&1)"; rc=$?
if (( rc == 3 )); then ok "(d) --model отклонён с exit 3"; else bad "(d) rc=${rc}, ждали 3"; fi
echo ""

# --- (e) входной гейт живости (настоящий api: 404 = мёртв) -------------------
echo "--- (e) гейт живости ---"
FRESH_DEAD="ses_fixmailprobe0000000000000000"
out="$(env PEER_MAIL_DIR="${PEER_MAIL_DIR}" "${LETTER}" --to "${FRESH_DEAD}" \
  --from ses_fixmailsender00000000000 --text "тест e" 2>&1)"; rc=$?
if (( rc == 1 )) && grep -q "адресат не найден" <<< "${out}"; then
  ok "(e1) несуществующий адресат -> REFUSE exit 1"
else
  bad "(e1) rc=${rc}, вывод: ${out:0:120}"
fi
out="$(env PEER_MAIL_DIR="${PEER_MAIL_DIR}" PEER_REGISTRY="${REG_FIXTURE}" \
  PATH="${TEST_MAIL}/bin-ok:${PATH}" \
  "${LETTER}" --to "${HAPPY_TARGET}" --from ses_fixmailsender00000000000 \
  --text "ТЕСТ (e2) гейт" 2>&1)"; rc=$?
if (( rc == 0 )) && ! grep -q "адресат не найден" <<< "${out}"; then
  ok "(e2) существующий адресат с агентом прошёл оба гейта (rc=0)"
else
  bad "(e2) rc=${rc}: $(echo "${out}" | tail -1)"
fi
echo ""

# --- (f) валидатор реестра (боевой, read-only) --------------------------------
echo "--- (f) validate-registry.py ---"
vout="$(python3 "${VALIDATOR}" 2>&1)"; vrc=$?
if [[ "${vout}" == *"Ведомство"* && "${vout}" == *"Статус"* && "${vout}" == *"Итого"* ]]; then
  ok "(f1) валидатор вывел таблицу с итогом"
else
  bad "(f1) неожиданный вывод валидатора"
fi
if [[ "${vout}" == *"NO-AGENT"* ]]; then ok "(f2) NO-AGENT ловится (ДВ-Хаб и др.)"; else bad "(f2) NO-AGENT не показан"; fi
if (( vrc == 0 || vrc == 1 )); then ok "(f3) exit-код валидатора валиден (0|1): ${vrc}"; else bad "(f3) странный rc=${vrc}"; fi
echo ""

# --- Итог ---------------------------------------------------------------------
echo "=== Результат: ${pass} passed, ${fail} failed ==="
(( fail == 0 )) && exit 0
exit 1
