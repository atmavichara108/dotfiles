#!/bin/bash
# Peer letter delivery — единственная канонная точка отправки письма в сессию.
#
# Проблема B15 → закрыта жёстко (мандат владельца 2026-10-18, B15 model-lock):
# `opencode run -s <id> -m <model>` вызывает серверную операцию session.switchModel
# и ПЕРСИСТЕНТНО переписывает модель в самой сессии адресата (opencode.db,
# session_v2.model). Канал не должен менять модель адресата никогда.
#
# Guard (мандат 2026-10-18, зеркалит peer-comms.md):
#   без --model    -> письмо уходит без switchModel; модель адресата не меняется
#   --model        -> REFUSE (exit 3) ВСЕГДА, без исключений
#   --force-model  -> флаг удалён целиком (обход гейтить нельзя); попадёт
#                     в "Unknown option" (exit 1)
#
# БД не изменяет. Журнал доставки (B18) — append-only receipts-out.jsonl в
# ~/.local/state/opencode/mail/ (metadata-only: id/digest/to/from/ts, без тела).
#
# Вежливая доставка (мандат polite-delivery-20261019, апрув владельца):
# перед инжектом проверяем, свободен ли адресат (opencode api GET /api/session:
# busy = time.updated > time.idle; сбой определения = свободен, fail-open).
# Занят -> payload копируется в MAIL_DIR/pending/<message_id>.txt и запись
# кладётся в MAIL_DIR/pending.jsonl; доставка — при ЛЮБОМ последующем вызове
# letter.sh (drain перед каждой отправкой), + ручной режим `letter.sh --drain`.
# Форс-таймаут LETTER_QUEUE_TTL (сек, default 1800 = 30 мин): запись старше —
# доставляется безусловно с пометкой (event=timeout, поле wait_ms в журнале).
# Очередь живёт на диске — переживает рестарт сервера. Payload копируется:
# /tmp-оригинал может исчезнуть.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAIMS_FILE="${CLAIMS_FILE:-${SCRIPT_DIR}/claims.jsonl}"
MAIL_DIR="${PEER_MAIL_DIR:-$HOME/.local/state/opencode/mail}"
# Scope C (мандат ЦУ agents-drwho-20261019, ВРЕМЕННАЯ мера; апрув владельца):
# агент адресата берём из peer-registry (колонка «Агент»), а не из дефолтов
# рабочего каталога вызывающего: cwd-дефолт («sysop» из dotfiles) не существует
# в репо забежавшего адресата (ability-lab -> Dr.Who) -> «Agent not found».
# Не резолвили/не нашли -> письмо уходит БЕЗ переключения агента, не падает.
# Постоянный фикс (агент как отдельное поле реестра/схема) — отдельное решение.
REGISTRY_FILE="${PEER_REGISTRY:-$HOME/Projects/OpenCode-Vault/04-Memory/peer-registry.md}"

fail() { echo "Error: $*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage:
  letter.sh --to <sessionID> [--title <t>] --file <path>
  letter.sh --to <sessionID> [--title <t>] --text "<message>"
  letter.sh --drain              обслужить отложенную очередь и выйти

Receipt-флаги (B18, двойной ack):
  --from <id>                 отправитель в журнал (дефолт $OPENCODE_SESSION_ID)
  --scope <s>                 метка scope в журнал
  --receipt <kind> --ref <message_id>
                              kind = started | finished | cannot; письмо-квитанция
                              (получатель шлёт started при получении, finished при
                              завершении хода). Тело письма обязательно содержит
                              ref — по нему доставка проверяется delivery-check.

Journal (append-only, metadata-only, без тела письма):
  ${PEER_MAIL_DIR:-~/.local/state/opencode/mail}/receipts-out.jsonl
  идемпотентность: повтор того же message_id (hash тела + день + from) — отклоняется.

Guard (B15 model-lock, мандат владельца 2026-10-18):
  --model      -> REFUSE (exit 3) всегда: канал не меняет модель адресата
  --force-model -> флаг удалён: "Unknown option" (exit 1)
EOF
}

journal_append() {
  # Одна короткая JSONL-строка; < PIPE_BUF, append атомарен без лока.
  local mail_dir="$1"; shift
  mkdir -p "${mail_dir}"
  printf '%s\n' "$*" >> "${mail_dir}/receipts-out.jsonl"
}

sha256_of() { printf '%s' "$1" | sha256sum | cut -d' ' -f1; }

# Agent адресата из peer-registry (Scope C, временная мера). Пусто = нет записи.
# Нормализация: "Dr.Who" -> dr-who (id агента — lowercase, точки -> дефисы).
registry_agent() {
  local target="${1:?}"
  [[ -r "${REGISTRY_FILE}" ]] || return 0
  awk -F'|' -v sid="${target}" '
    /^[|]/ && $3 ~ sid {
      v = $4
      gsub(/\*/, "", v)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
      if (v == "" || v == "Агент" || /^-+$/) v = ""
      print v
      exit
    }' "${REGISTRY_FILE}" 2>/dev/null \
    | tr '[:upper:]' '[:lower:]' | tr '.' '-'
}

PENDING_FILE="${MAIL_DIR}/pending.jsonl"
PENDING_DIR="${MAIL_DIR}/pending"
QUEUE_TTL="${LETTER_QUEUE_TTL:-1800}"   # форс-таймаут, сек (default 30 мин)

# busy адресата по API (мандат: API-путь предпочтителен).
# busy = time.updated > time.idle. Сбой API = свободен (fail-open, не голодает).
session_busy() {
  local target="${1:?}"
  local json
  json="$(opencode api get "/api/session/${target}" 2>/dev/null)" || return 1
  local idle updated
  idle="$(jq -r '.data.time.idle // 0' <<< "${json}" 2>/dev/null)"
  updated="$(jq -r '.data.time.updated // 0' <<< "${json}" 2>/dev/null)"
  if [[ -z "${idle}" || -z "${updated}" ]]; then return 1; fi
  (( updated > idle ))
}

# Инжект по готовому args + запись в журнал. Используется и прямым
# путём, и из drain. $1 = message_id, $2 = digest, $3.. = argv для opencode.
# INJECT_EVENT: "sent" или "receipt-<kind>" (квитанции B18).
_inject() {
  local mid="$1" dg="$2"; shift 2
  journal_append "${MAIL_DIR}" "$(jq -cn \
    --arg event "${INJECT_EVENT:-sent}" --arg id "${mid}" --arg digest "${dg}" \
    --arg to "${TO}" --arg from "${FROM}" --arg scope "${SCOPE}" --arg ref "${REF}" \
    '{event:$event, message_id:$id, digest:$digest, to:$to, from:$from,
      scope:$scope, ref:$ref, ts:(now|floor)}')"
  echo "RECEIPT: ${mid} -> ${TO} (journal: ${MAIL_DIR}/receipts-out.jsonl)" >&2
  local rc=0
  opencode "$@" || rc=$?
  if (( rc != 0 )); then
    journal_append "${MAIL_DIR}" "$(jq -cn \
      --arg id "${mid}" --argjson rc "${rc}" \
      '{event:"run-rc", message_id:$id, rc:$rc, ts:(now|floor)}')"
  fi
  return "${rc}"
}

# Обслужить отложенную очередь: свободен -> доставить; занят дольше QUEUE_TTL ->
# доставить безусловно (event=timeout, wait_ms в журнале); иначе продолжает ждать.
# Вызывается перед каждой отправкой и режимом --drain.
drain_queue() {
  [[ -s "${PENDING_FILE}" ]] || return 0
  local tmp now age mid dg pt qs payload_line target from_field scope_field busy
  tmp="${PENDING_FILE}.tmp"
  : > "${tmp}"
  now=$(date +%s)
  while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    mid="$(jq -r '.message_id // ""' <<< "${line}")"
    dg="$(jq -r '.digest // ""' <<< "${line}")"
    pt="$(jq -r '.payload_path // ""' <<< "${line}")"
    qs="$(jq -r '.queued_ts // 0' <<< "${line}")"
    target="$(jq -r '.to // ""' <<< "${line}")"
    from_field="$(jq -r '.from // ""' <<< "${line}")"
    scope_field="$(jq -r '.scope // ""' <<< "${line}")"
    age=$(( now - qs ))
    payload_line="$(cat "${pt}" 2>/dev/null || true)"
    if [[ -z "${target}" || -z "${payload_line}" ]]; then
      echo "drain: битая запись (нет payload/to) mid=${mid}" >&2
      continue
    fi
    busy=0
    session_busy "${target}" && busy=1
    if (( busy == 1 && age < QUEUE_TTL )); then
      printf '%s\n' "${line}" >> "${tmp}"
      continue
    fi
    local note="" event="sent"
    if (( busy == 1 )); then event="timeout"; note=" (delivered-after-timeout)"; fi
    journal_append "${MAIL_DIR}" "$(jq -cn \
      --arg event "${event}" --arg id "${mid}" --arg digest "${dg}" \
      --arg to "${target}" --arg from "${from_field}" --arg scope "${scope_field}" \
      --argjson wait_ms $(( age * 1000 )) \
      '{event:$event, message_id:$id, digest:$digest, to:$to, from:$from,
        scope:$scope, wait_ms:$wait_ms, ts:(now|floor)}')"
    echo "RECEIPT: ${mid} -> ${target}${note} (journal)" >&2
    local rrc=0
    opencode run -s "${target}" -- "${payload_line}" 2>/dev/null || rrc=$?
  done < "${PENDING_FILE}"
  mv "${tmp}" "${PENDING_FILE}"
}

# Положить письмо в очередь (payload копируем: /tmp может протухнуть).
enqueue_pending() {
  mkdir -p "${PENDING_DIR}"
  local pp="${PENDING_DIR}/${MESSAGE_ID}.txt"
  printf '%s' "${PAYLOAD}" > "${pp}"
  jq -c -n \
    --arg mid "${MESSAGE_ID}" --arg digest "${DIGEST}" \
    --arg to "${TO}" --arg from "${FROM}" --arg scope "${SCOPE}" \
    --arg title "${TITLE}" --arg pp "${pp}" \
    --argjson queued_ts "$(date +%s)" \
    '{op:"queued", message_id:$mid, digest:$digest, to:$to, from:$from,
      scope:$scope, title:$title, payload_path:$pp, queued_ts:$queued_ts, attempts:0}' \
    >> "${PENDING_FILE}"
  echo "QUEUED: ${MESSAGE_ID} -> ${TO} (адресат занят; ${QUEUE_TTL}s TTL; ${PENDING_FILE})" >&2
}

main() {
  local to="" title="" text="" file=""
  local from="${OPENCODE_SESSION_ID:-unknown}" scope="" receipt="" ref=""
  local DRAIN=0
  while (( $# > 0 )); do
    case "$1" in
      --drain)       DRAIN=1; shift ;;
      --to)          to="${2:?--to requires a value}"; shift 2 ;;
      --model)       echo "REFUSE: --model запрещён (B15 model-lock, мандат владельца 2026-10-18): канал не меняет модель адресата; смена модели — только владелец штатными средствами" >&2; exit 3 ;;
      --title)       title="${2:?--title requires a value}"; shift 2 ;;
      --text)        text="${2:?--text requires a value}"; shift 2 ;;
      --file)        file="${2:?--file requires a value}"; shift 2 ;;
      --from)        from="${2:?--from requires a value}"; shift 2 ;;
      --scope)       scope="${2:?--scope requires a value}"; shift 2 ;;
      --receipt)     receipt="${2:?--receipt requires a value}"; shift 2 ;;
      --ref)         ref="${2:?--ref requires a value}"; shift 2 ;;
      # --force-model удалён целиком (обход гейтить нельзя) — попадёт в
      # "Unknown option" ниже автоматически.
      -h|--help|help) usage; return 0 ;;
      *) fail "Unknown option: $1" ;;
    esac
  done

  # Вежливая доставка: очередь обслуживается при каждом обращении к каналу.
  if (( DRAIN == 1 )); then
    drain_queue
    return 0
  fi

  [[ -n "${to}" ]] || fail "--to is required"
  [[ -n "${text}" || -n "${file}" ]] || fail "--text or --file is required"
  if [[ -n "${receipt}" ]]; then
    [[ "${receipt}" =~ ^(started|finished|cannot)$ ]] || fail "--receipt: started|finished|cannot"
    [[ -n "${ref}" ]] || fail "--receipt requires --ref <message_id оригинала>"
  fi

  # --file: текст письма читается из файла (канон против shell-quote багов)
  local payload
  if [[ -n "${file}" ]]; then
    [[ -f "${file}" ]] || fail "--file not found: ${file}"
    payload="$(cat "${file}")"
  else
    payload="${text}"
  fi

  # NOTE (B15 model-lock): никаких -m/--model и no force-пути. Модель адресата
  # канал не меняет никогда — смена только владельцем штатными средствами.

  # message_id: детерминированный — hash тела + номер дня + from (спека S2.1)
  local digest message_id
  digest="$(sha256_of "${payload}")"
  message_id="${digest:0:16}-$(date -u +%Y%m%d)-${from}"

  # Garbage-guard (инцидент 2026-10-07): не выпускать decode-мусор в живые
  # сессии команды. REFUSE до записи в журнал и до отправки. Канон B15/B18
  # не затронут: это проверка текста, не модели и не receipts.
  # Обход: GARBAGE_OK=1 (осознанно, как MIXED_OK).
  local guard_script="${SCRIPT_DIR}/../garbage-guard/guard.py"
  if [[ -f "${guard_script}" && "${GARBAGE_OK:-0}" != "1" ]]; then
    local guard_rc=0
    printf '%s' "${payload}" | python3 "${guard_script}" check-text 2>/dev/null || guard_rc=$?
    if [[ "${guard_rc}" == 1 ]]; then
      echo "REFUSE: текст письма содержит decode-мусор (CJK/kana/FFFD — инцидент 2026-10-07)." >&2
      echo "REFUSE: проверь вывод 'python3 tools/garbage-guard/guard.py check-text < файл'. Обход: GARBAGE_OK=1" >&2
      exit 4
    fi
    # guard_rc==2 (ошибка инструмента) — не блокируем жизнь, тихо пропускаем
  fi

  # Идемпотентность (S2.2): повтор того же message_id — отклоняется, не дублирует.
  local out_file="${MAIL_DIR}/receipts-out.jsonl"
  if [[ -f "${out_file}" ]] && grep -qF "\"message_id\":\"${message_id}\"" "${out_file}"; then
    echo "DUP: message_id=${message_id} уже в журнале — повтор отклонён (no-resend)" >&2
    return 0
  fi

  # Вежливая доставка (polite-delivery-20261019): сначала обслуживаем очередь
  # (старые письма идут первыми), затем idle-гейт для этого письма.
  TO="${to}" FROM="${from}" SCOPE="${scope}" REF="${ref}" TITLE="${title}"
  DIGEST="${digest}" MESSAGE_ID="${message_id}" PAYLOAD="${payload}"
  INJECT_EVENT=$([[ -n "${receipt}" ]] && echo "receipt-${receipt}" || echo "sent")
  drain_queue
  if session_busy "${to}"; then
    enqueue_pending
    return 0
  fi

  local args=("run" "-s" "${to}")
  [[ -n "${title}" ]] && args+=("--title" "${title}")
  # терминал `--` ОБЯЗАТЕЛЕН (BF-20261018-03): payload из файла может начинаться
  # с "- " (список) — CLI трактует такой аргумент как флаг и показывает help,
  # письмо молча не доставляется. `--` гарантированно переводит payload
  # в позиционный аргумент.
  args+=("--" "${payload}")

  # Scope C (agents-drwho-20261019): агент адресата — из реестра, не из cwd.
  # Знаем -> --agent <имя> (run переключит/подтвердит агента адресата на его же
  # штатного, «Agent not found: sysop» уходит). Не знаем -> как раньше, без
  # --agent. Если --agent отклонён адресатом — НЕ падаем: доставка без
  # переключения агента, с пометкой agent-fallback в журнале.
  local ragent fa_rc=0
  ragent="$(registry_agent "${to}")"
  if [[ -n "${ragent}" ]]; then
    local base_args=("${args[@]}")
    args+=("--agent" "${ragent}")
    _inject "${message_id}" "${digest}" "${args[@]}" || fa_rc=$?
    if (( fa_rc != 0 )); then
      journal_append "${MAIL_DIR}" "$(jq -cn \
        --arg event "agent-fallback" --arg id "${message_id}" \
        --arg agent "${ragent}" \
        '{event:"agent-fallback", message_id:$id, agent:$agent, ts:(now|floor)}')"
      echo "NOTE: --agent ${ragent} отклонён адресатом -> доставка без переключения агента" >&2
      _inject "${message_id}" "${digest}" "${base_args[@]}"
    fi
  else
    _inject "${message_id}" "${digest}" "${args[@]}"
  fi
}

main "$@"