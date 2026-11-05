#!/usr/bin/env bash
# guard-watchdog — страховка для portal-tg-guard.
#
# Причина (инцидент 2026-11-04 16:06 МСК): умер SOCKS-прокси, Telethon не
# переподключился, служба получила SIGTERM и легла. Restart=always не помогает,
# когда юнит остановлен штатно — тогда он просто остаётся мёртвым, и портал
# молчит сутками.
#
# Что делает: если служба не active — поднимает и пишет строку в журнал
# сторожа. Тихий при живом; громкий только когда чинит. Секретов не трогает.
set -uo pipefail

STATE_DIR="${HOME}/.local/state/portal-tg"
LOG="${STATE_DIR}/watchdog.jsonl"
UNIT="portal-tg-guard.service"

state="$(systemctl --user is-active "${UNIT}" 2>/dev/null || true)"
if [[ "${state}" == "active" ]]; then
    exit 0
fi

mkdir -p "${STATE_DIR}"
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "{\"ts\":\"${ts}\",\"unit\":\"${UNIT}\",\"state\":\"${state}\",\"action\":\"restart\"}" >> "${LOG}"

systemctl --user start "${UNIT}" >/dev/null 2>&1
sleep 5
after="$(systemctl --user is-active "${UNIT}" 2>/dev/null || true)"
echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"unit\":\"${UNIT}\",\"state_before\":\"${state}\",\"state_after\":\"${after}\"}" >> "${LOG}"

[[ "${after}" == "active" ]] || exit 1
exit 0
