#!/bin/bash
# tests-waits-dedup — приёмка У-7 операции «Гомеостаз»: одно дело = одна строка.
#
# Дефект найден живьём: ручной `waits.py add --ref X` и авто-строка из
# `ship-mail.sh send --task --ref X` создавали ДВЕ строки ожидания на одно дело,
# и адресат получал два пинка по одному и тому же.
#
# Проверяется:
#   1) ручная строка + send --task с тем же ref+адресатом -> строка ОДНА;
#   2) send --task с ДРУГИМ ref -> строка создаётся (дедуп не глушит работу);
#   3) повтор отбивается явно, а не молча и не как «создана»;
#   4) закрытое дело (stitch) не блокирует повторную постановку.
#
# Изоляция: временный SHIP_MAIL_HOME и снапшот реестра, боевые файлы не трогаются.
# Запуск: bash tools/ship-mail/tests-waits-dedup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WAITS="${SCRIPT_DIR}/waits.py"
SHIP="${SCRIPT_DIR}/ship-mail.sh"

WORK_DIR="$(mktemp -d /tmp/opencode/waits-dedup.XXXXXX)"
trap 'rm -rf "${WORK_DIR}"' EXIT

export SHIP_MAIL_HOME="${WORK_DIR}/home"
mkdir -p "${SHIP_MAIL_HOME}"
export SHIP_MAIL_REGISTRY="${HOME}/Projects/OpenCode-Vault/04-Memory/peer-registry.md"
export SHIP_MAIL_REGISTRY_SNAPSHOT="${WORK_DIR}/registry.snapshot.md"

OURS="ses_ece7b76c8ffeOkYZqZe38QbTVx"
THEIRS="ses_eceb23a71ffeJO9QnFou8VngZC"

waits="${SHIP_MAIL_HOME}/waits.jsonl"

# Тело письма уникально на каждый вызов: ship-mail отбивает полные дубли
# (body+from+day), иначе тест мерил бы дедуп транспорта, а не очереди.
mkletter() {
  local path="$1" tag="$2"
  cat > "${path}" <<LETTER
## СДЕЛАНО
- приёмочный тест дедупликации, метка ${tag}

## ЗАБЛОКИРОВАНО
- нет

## ЖДЁТ-ЗАБОТЫ
- ответить строкой

После выполнения — продолжай свою работу.
LETTER
}

pass=0
fail=0
ok()  { echo "  PASS: $1"; pass=$(( pass + 1 )); }
bad() { echo "  FAIL: $1"; echo "        $2"; fail=$(( fail + 1 )); }

echo "=== У-7: одно дело = одна строка ожидания ==="

# --- 1) ручная строка + автоматическая по тому же ref
python3 "${WAITS}" add --owe "${THEIRS}" --what "приёмочный дедуп" --by "${OURS}" \
  --ref dedup-A --ttl-minutes 30 >/dev/null
mkletter "${WORK_DIR}/l1.md" "A1"
bash "${SHIP}" send --to "${THEIRS}" --from "${OURS}" --title "приёмочный дедуп A1" \
  --ref dedup-A --task --file "${WORK_DIR}/l1.md" >/dev/null 2>&1 || true

n_a="$(grep -c '"ref": "dedup-A"' "${waits}" 2>/dev/null || true)"
if [[ "${n_a}" == "1" ]]; then
  ok "дело dedup-A стоит в очереди одной строкой (не двумя)"
else
  bad "дело dedup-A стоит в очереди одной строкой" "строк с ref dedup-A: ${n_a}"
fi

# --- 2) новый ref -> строка создаётся
mkletter "${WORK_DIR}/l2.md" "B conf"
bash "${SHIP}" send --to "${THEIRS}" --from "${OURS}" --title "приёмочный дедуп B1" \
  --ref dedup-B --task --file "${WORK_DIR}/l2.md" >/dev/null 2>&1 || true

if grep -q '"ref": "dedup-B"' "${waits}"; then
  ok "другое дело (dedup-B) поставлено в очередь"
else
  bad "другое дело (dedup-B) поставлено в очередь" "строки dedup-B нет"
fi

# --- 3) повтор отбивается явно
mkletter "${WORK_DIR}/l3.md" "A repeat"
out="$(bash "${SHIP}" send --to "${THEIRS}" --from "${OURS}" --title "приёмочный дедуп A2" \
        --ref dedup-A --task --file "${WORK_DIR}/l3.md" 2>&1 || true)"
if [[ "${out}" == *"уже стоит"* && "${out}" != *"строка-ожидание создана"* ]]; then
  ok "повтор сообщает «уже стоит», а не «создана»"
elif [[ "${out}" == *"уже отправлен"* || "${out}" == *duplicate* ]]; then
  ok "повтор отбит явно (письмо с этим ref уже отправлено)"
else
  bad "повтор сообщает «уже стоит», а не «создана»" "${out}"
fi

# --- 4) дело закрыто (stitch) -> место освобождается, новая строка законна
python3 "${WAITS}" add --owe "${THEIRS}" --what "приёмочный C" --by "${OURS}" \
  --ref dedup-C --ttl-minutes 30 >/dev/null
wid_c="$(python3 - "${waits}" <<'PY'
import json, sys
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if line:
        r = json.loads(line)
        if r.get("ref") == "dedup-C":
            print(r["id"])
            break
PY
)"
python3 "${WAITS}" stitch "${wid_c}" --reply-to x --answered-by "${THEIRS}" \
  --answered-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --evidence тест >/dev/null 2>&1 || true
python3 "${WAITS}" add --owe "${THEIRS}" --what "приёмочный C повтор" --by "${OURS}" \
  --ref dedup-C --ttl-minutes 30 >/dev/null

open_c="$(python3 - "${waits}" <<'PY'
import json, sys
n = 0
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if line:
        r = json.loads(line)
        if r.get("ref") == "dedup-C" and r.get("state", "open") == "open":
            n += 1
print(n)
PY
)"
if [[ "${open_c}" == "1" ]]; then
  ok "закрытое дело не блокирует повторную постановку"
else
  bad "закрытое дело не блокирует повторную постановку" "открытых dedup-C: ${open_c}"
fi

echo "=== ${pass} pass, ${fail} fail ==="
(( fail == 0 )) || exit 1
exit 0
