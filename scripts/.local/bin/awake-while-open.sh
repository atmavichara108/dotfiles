#!/usr/bin/env bash
# awake-while-open: ноут не спит НИ ПРИ ОТКРЫТОЙ, НИ ПРИ ЗАКРЫТОЙ крышке.
# Эволюция 2026-10-17 (слово владельца): «при закрытии крышки ничего не
# происходило и ноут работал так же» → держим ПЕРМАНЕНТНЫЙ блокирующий
# ингибитор sleep:handle-lid-switch:idle: закрытие крышки игнорируется
# logind, suspend от любых idle-источников заблокирован. Сон — только
# вручную (systemctl suspend / кнопка).
# Дедлайн 24ч временной версии снят: фича постоянная.
# lid-мониторинг не нужен — крышка больше не управляет ничем.
# Вернуть штатное поведение: systemctl --user disable --now awake-while-open.
set -euo pipefail
CHILD=""
ensure() {
  if [ -z "$CHILD" ] || ! kill -0 "$CHILD" 2>/dev/null; then
    systemd-inhibit --what=sleep:handle-lid-switch:idle \
      --who=awake-while-open \
      --why="владелец: крышка не влияет на сон, ноут работает всегда" \
      --mode=block sleep infinity &
    CHILD=$!
  fi
}
cleanup() { if [ -n "$CHILD" ]; then kill "$CHILD" 2>/dev/null || true; wait "$CHILD" 2>/dev/null || true; CHILD=""; fi; }
trap cleanup EXIT
trap 'cleanup; exit 0' TERM INT
while :; do
  ensure
  sleep 15
done
