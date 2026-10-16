#!/usr/bin/env bash
# Держит idle-inhibitor, пока крышка открыта; при закрытой — отпускает.
# Deadline 24ч: после — выход с кодом 2 (юнит больше не рестартует).
set -euo pipefail
LID_GLOB=/proc/acpi/button/lid/*/state
CHILD=""
END=$(( $(date +%s) + 24*3600 ))
lid_open() { grep -qi open $LID_GLOB 2>/dev/null; }
ensure() {
  if [ -z "$CHILD" ] || ! kill -0 "$CHILD" 2>/dev/null; then
    systemd-inhibit --what=idle --who=awake-while-open \
      --why="работа владельца, крышка открыта" --mode=block sleep 900 &
    CHILD=$!
  fi
}
drop() {
  if [ -n "$CHILD" ]; then kill "$CHILD" 2>/dev/null || true; wait "$CHILD" 2>/dev/null || true; CHILD=""; fi
}
cleanup() { drop; }
trap cleanup EXIT
trap 'cleanup; exit 0' TERM INT
while :; do
  if [ "$(date +%s)" -ge "$END" ]; then
    echo "awake-while-open: deadline 24ч истёк — выключение" >&2
    exit 2
  fi
  if lid_open; then ensure; else drop; fi
  sleep 15
done
