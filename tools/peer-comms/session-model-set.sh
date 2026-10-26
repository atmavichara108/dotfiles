#!/bin/bash
# session-model-set.sh — смена модели сессии ТОЛЬКО с проверкой результата.
#
# Причина (инцидент inc-silent-success-20261025, ИПТ → ИЦ): прямой POST
# /api/session/<id>/model отвечает ПУСТЫМ выводом с кодом 0 — «пустой ответ
# + exit 0» агент принимал за успех и рапортовал «модель переключена» без
# доказательства. Класс-урок: любой state-change с пустым ответом обязан
# завершаться read-back-проверкой В ТОЙ ЖЕ команде.
#
# Использование:
#   session-model-set.sh <sessionID> <providerID>/<modelID>
#
# Поведение:
#   1. POST смены модели (как у канала: basic-auth из service.json);
#   2. ОБЯЗАТЕЛЬНО GET /api/session/<id> — читаем состояние назад;
#   3. Сверяем provider+model. Расхождение (включая вариант) — печать diff
#      «хотел/стало» и exit 1. Успех ТОЛЬКО при полном совпадении — exit 0.
#
# Выходные коды: 0 ок · 1 не совпало/не применилось · 2 usage/API-сбой.
# Секреты не печатаются (токен только в заголовке).

set -euo pipefail

ENDPOINT="${OPENCODE_ENDPOINT:-http://127.0.0.1:49374}"
SERVICE_JSON="${SERVICE_JSON:-$HOME/.config/opencode/service.json}"
SERVICE_USER="${OPENCODE_SERVICE_USER:-opencode}"

die() { echo "session-model-set: $1" >&2; exit "${2:-2}"; }

[ $# -eq 2 ] || die "usage: session-model-set.sh <sessionID> <providerID>/<modelID>" 2

SID="$1"
SPEC="$2"
case "$SID" in ses_*) ;; *) die "sessionID должен начинаться с ses_" 2 ;; esac
case "$SPEC" in */*) ;; *) die "модель в формате providerID/modelID (напр. nvidia/z-ai/glm-5.3)" 2 ;; esac
WANT_P="${SPEC%%/*}"
WANT_M="${SPEC#*/}"

[ -r "$SERVICE_JSON" ] || die "нет service.json: $SERVICE_JSON" 2
TOK="$(python3 -c "import json;d=json.load(open('$SERVICE_JSON'));print(d.get('password',''))" 2>/dev/null || true)"
[ -n "$TOK" ] || die "пустой токен в $SERVICE_JSON" 2
AUTH="Basic $(printf '%s:%s' "$SERVICE_USER" "$TOK" | base64 -w0)"

# 1. POST смены модели (пустой ответ — НЕ доказательство)
code="$(curl -sS -o /dev/null -w '%{http_code}' -X POST \
  -H "Authorization: $AUTH" -H "Content-Type: application/json" \
  -d "{\"model\":{\"providerID\":\"$WANT_P\",\"id\":\"$WANT_M\"}}" \
  "$ENDPOINT/api/session/$SID/model" 2>/dev/null || echo 000)"
case "$code" in
  2*) ;; # 2xx = принято (может быть пустым — читаем назад)
  000) die "POST недоступен (нет связи с $ENDPOINT)" 2 ;;
  *) die "POST вернул HTTP $code" 2 ;;
esac

# 2+3. read-back и сравнение
GOT="$(curl -sS -H "Authorization: $AUTH" "$ENDPOINT/api/session/$SID" 2>/dev/null || true)"
[ -n "$GOT" ] || die "read-back: пустой ответ GET $ENDPOINT/api/session/$SID" 2

read -r GOT_P GOT_M GOT_V <<<"$(printf '%s' "$GOT" > /tmp/opencode/.sms-$$.json && python3 -c "
import json
d=json.load(open('/tmp/opencode/.sms-$$.json'))
if isinstance(d, dict): d=d.get('data', d)
m=d.get('model') or {}
print(m.get('providerID','-'), m.get('id','-'), m.get('variant','-'))" 2>/dev/null || echo '- - -')"
[ "$GOT_P" != "-" ] || die "read-back: не удалось разобрать состояние сессии" 2

if [ "$GOT_P" = "$WANT_P" ] && [ "$GOT_M" = "$WANT_M" ]; then
  echo "OK: $SID -> $GOT_P/$GOT_M (variant=$GOT_V) — подтверждено чтением назад"
  exit 0
fi

echo "НЕ ПРИМЕНИЛОСЬ (exit 1):" >&2
echo "  хотел: $WANT_P/$WANT_M" >&2
echo "  стало: $GOT_P/$GOT_M (variant=$GOT_V)" >&2
exit 1
