#!/bin/bash
# tests-registry-canon — приёмка мандата ЦУ ic-registry-snapshot-20261108.
#
# Требование: источник снапшота реестра для ship-mail — КАНОН из git (main),
# а не живое дерево checkout'а. Тест: отправка с checkout'а, в рабочем дереве
# которого реестра нет (или он устарел), проходит по канонической версии.
#
# Изоляция: временный волт (git-репо), временная MAIL_HOME, временный SHIP_MAIL_VAULT.
# Запуск: bash tools/ship-mail/tests-registry-canon.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHIP="${SCRIPT_DIR}/ship-mail.sh"

WORK_DIR="$(mktemp -d /tmp/opencode/registry-canon.XXXXXX)"
trap 'rm -rf "${WORK_DIR}"' EXIT

VAULT="${WORK_DIR}/vault"
MAIL="${WORK_DIR}/mail"
mkdir -p "${VAULT}/04-Memory" "${MAIL}/inbox/ses_OWNERSESSIONDEL" "$HOME/.local/state/opencode"
cd "${VAULT}"
git init -q .
git config user.email t@t; git config user.name t

# Фикстура адресатов: обе линии + отправитель
cat > 04-Memory/peer-registry.md <<'REG'
| Ведомство | Сессия | Агент | Каталог | Зона |
|---|---|---|---|---|
| Отправитель | ses_OWNERSESSIONDEL | builder | ~/dotfiles | тест |
| Получатель | ses_TARGETSESSIONDEL | builder | ~/dotfiles | тест |
REG
git add -A && git commit -qm "registry canon"

pass=0; fail=0
ok()  { echo "  PASS: $1"; (( ++pass )); }
bad() { echo "  FAIL: $1"; echo "        $2"; (( ++fail )); }

echo "=== реестр как канон (не живое дерево) ==="

# 1) реестра нет в рабочем дереве → отправка всё равно проходит (канон из main)
mv 04-Memory/peer-registry.md "${WORK_DIR}/reg.bak"
out="$(SHIP_MAIL_VAULT="${VAULT}" SHIP_MAIL_HOME="${MAIL}" \
        bash "${SHIP}" send --to ses_TARGETSESSIONDEL --from ses_OWNERSESSIONDEL \
        --title "тест канона" --ref "test-canon-1" \
        --text $'## СДЕЛАНО\n- проверка\n\n## ЗАБЛОКИРОВАНО\n- нет\n\n## ЖДЁТ-ЗАБОТЫ\n- нет\n\nПосле выполнения — продолжай свою работу.' 2>&1)" || true
if [[ "${out}" == *DELIVERED* || "${out}" == *LINT* ]]; then
  ok "отправка без файла реестра в дереве проходит (канон main)"
else
  bad "отправка без файла реестра в дереве проходит" "${out}"
fi
ls "${MAIL}/inbox/ses_TARGETSESSIONDEL"/*.md >/dev/null 2>&1 \
  && ok "письмо легло в ящик адресата" || bad "письмо легло в ящик адресата" "нет файла"

# 2) реестр в дереве устарел (без адресата) → канон всё равно даёт адрес
printf '%s\n' '| Ведомство | Сессия | Агент | Каталог | Зона |' '|---|---|---|---|---|' \
  '| Отправитель | ses_OWNERSESSIONDEL | builder | ~/dotfiles | тест |' \
  > 04-Memory/peer-registry.md
out="$(SHIP_MAIL_VAULT="${VAULT}" SHIP_MAIL_HOME="${MAIL}" \
        bash "${SHIP}" send --to ses_TARGETSESSIONDEL --from ses_OWNERSESSIONDEL \
        --title "тест канона 2" --ref "test-canon-2" \
        --text $'## СДЕЛАНО\n- проверка\n\n## ЗАБЛОКИРОВАНО\n- нет\n\n## ЖДЁТ-ЗАБОТЫ\n- нет\n\nПосле выполнения — продолжай свою работу.' 2>&1)" || true
if [[ "${out}" == *DELIVERED* || "${out}" == *LINT* ]]; then
  ok "устаревшее дерево не отменяет канон (отправка прошла)"
else
  bad "устаревшее дерево не отменяет канон" "${out}"
fi

echo "=== ${pass} pass, ${fail} fail ==="
(( fail == 0 )) || exit 1
exit 0
