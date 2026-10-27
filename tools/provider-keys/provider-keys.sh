#!/bin/bash
# provider-keys — мост «секрет провайдера → environment.d» для OpenCode.
#
# Канон: секретов в репо нет; сервер ворот (owner-gate) пишет секрет файлом
# в ~/.secrets/<file> (600) серверной записью — значение не покидает процесс
# ворот и не проходит через агента/лог. OpenCode-конфиг читает ключ из
# окружения сервера (`{env:VAR}`). Этот скрипт — штатный мост между ними:
# из сырого секрета делает корректный environment.d-файл, не выводя секрет
# в поток вывода и не требуя от агента его прочитать.
#
# Реестр (tools/provider-keys/registry.json) хранит ТОЛЬКО имена:
#   [{"provider":"apinex","env":"APINEX_API_KEY","secret_file":"apinex.key"}]
# (провайдер → переменная окружения → файл-секрет). Значений — никогда.
#
# Команды:
#   provider-keys.sh add <provider> <ENV_VAR> <secret_file>
#   provider-keys.sh env <provider>     — пересобрать environment.d-файл провайдера
#   provider-keys.sh env --all          — пересобрать все
#   provider-keys.sh check              — проверить полноту: каждый {env:VAR} конфига
#                                        имеет источник и непустой environment.d
#
# Выход check: 0 — всё сходится; 1 — есть долги (список в stdout).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REGISTRY="${ROOT}/tools/provider-keys/registry.json"
ENVD_DIR="${HOME}/.config/environment.d"
SECRET_DIR="${HOME}/.secrets"
CONFIG_FILE="${ROOT}/opencode-global/.config/opencode/opencode.json"

[[ -r "${REGISTRY}" ]] || { echo "нет реестра: ${REGISTRY}" >&2; exit 2; }

cmd="${1:-}"; shift || true

jqr() { jq -r "$@" "${REGISTRY}"; }

build_env_file() {
  local provider="$1" envvar secret_file src dst
  envvar="$(jqr --arg p "$provider" '.[] | select(.provider==$p) | .env')"
  secret_file="$(jqr --arg p "$provider" '.[] | select(.provider==$p) | .secret_file')"
  [[ -n "${envvar}" && -n "${secret_file}" ]] || { echo "$provider: нет в реестре" >&2; return 1; }
  src="${SECRET_DIR}/${secret_file}"
  dst="${ENVD_DIR}/${provider}.conf"
  if [[ ! -s "${src}" ]]; then
    echo "$provider: секрет пуст/отсутствует (${src})" >&2
    return 1
  fi
  umask 077
  { printf '%s=' "${envvar}"; cat "${src}"; printf '\n'; } > "${dst}"
  chmod 600 "${dst}"
  echo "$provider: ${dst} пересобран (600)"
}

case "${cmd}" in
  add)
    provider="${1:-}"; envvar="${2:-}"; secret_file="${3:-}"
    [[ -n "${provider}" && -n "${envvar}" && -n "${secret_file}" ]] || {
      echo "использование: provider-keys.sh add <provider> <ENV_VAR> <secret_file>" >&2; exit 2; }
    [[ "${envvar}" =~ ^[A-Z][A-Z0-9_]*$ ]] || { echo "ENV_VAR — только A-Z0-9_" >&2; exit 2; }
    tmp="$(mktemp)"; jq --arg p "${provider}" --arg e "${envvar}" --arg s "${secret_file}" \
      '. += [{provider:$p, env:$e, secret_file:$s}] | unique_by(.provider)' "${REGISTRY}" > "${tmp}"
    mv "${tmp}" "${REGISTRY}"
    echo "зарегистрирован: $provider -> \${$envvar} <- ~/.secrets/$secret_file"
    ;;
  env)
    if [[ "${1:-}" == "--all" ]]; then
      for p in $(jqr '.[].provider'); do build_env_file "$p" || true; done
    else
      build_env_file "${1:?провайдер}"
    fi
    ;;
  check)
    debts=0
    # 1. каждый {env:VAR} в конфиге провайдеров имеет запись в реестре
    for var in $(grep -o '{env:[A-Z0-9_]*}' "${CONFIG_FILE}" 2>/dev/null | sed 's/{env:\(.*\)}/\1/' | sort -u); do
      if ! jq -e --arg v "$var" 'any(.[]; .env==$v)' "${REGISTRY}" >/dev/null; then
        echo "ДОЛГ: ${var} есть в конфиге, но нет в реестре"; debts=1
      fi
    done
    # 2. каждый провайдер реестра: секрет есть, environment.d-файл непуст
    for p in $(jqr '.[].provider'); do
      envvar="$(jqr --arg p "$p" '.[] | select(.provider==$p) | .env')"
      sf="$(jqr --arg p "$p" '.[] | select(.provider==$p) | .secret_file')"
      [[ -s "${SECRET_DIR}/${sf}" ]] || { echo "ДОЛГ: $p — секрет отсутствует (~/.secrets/$sf)"; debts=1; }
      conf="${ENVD_DIR}/${p}.conf"
      val="$(grep -m1 "^${envvar}=" "${conf}" 2>/dev/null | sed "s/^${envvar}=//")"
      if [[ -z "${val}" ]]; then echo "ДОЛГ: $p — ${conf} пуст (выполни: provider-keys.sh env $p)"; debts=1; fi
    done
    (( debts == 0 )) && echo "OK: все провайдеры сходятся" || true
    exit $(( debts == 0 ? 0 : 1 ))
    ;;
  *) echo "использование: provider-keys.sh {add|env|check}" >&2; exit 2 ;;
esac
