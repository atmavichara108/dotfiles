#!/bin/zsh
# Решающий тест: v3-шим на 8785 против РЕАЛЬНОГО апстрима, большой payload.
cd /home/rudra/dotfiles/opencode-global/.config/opencode/shim
LOG=/tmp/opencode/jw/v3-real.log
: > "$LOG"
PORT=8785 UPSTREAM_BASE=https://api.justwoker.icu/v1 HANG_MS=45000 UPSTREAM_TIMEOUT_MS=120000 \
  bun run justwoker-shim.ts > "$LOG" 2>&1 &
SHIMPID=$!
echo "v3-real pid=$SHIMPID"
sleep 3
curl -s -o /dev/null -w "health8785=%{http_code}\n" --max-time 5 http://127.0.0.1:8785/health

KEY=$(jq -r '.justwoker.key' ~/.local/share/opencode/auth.json)
echo "--- большой payload (796KB) через v3 к реальному апстриму ---"
curl -sN -o /tmp/opencode/jw/v3-big-resp.txt -w "http=%{http_code} t=%{time_total}s\n" \
  --max-time 100 -X POST http://127.0.0.1:8785/v1/messages \
  -H "x-api-key: $KEY" -H "anthropic-version: 2023-06-01" -H "content-type: application/json" \
  -d @/tmp/opencode/jw/big.json
echo "ответ (первые 200 байт):"
head -c 200 /tmp/opencode/jw/v3-big-resp.txt
echo
echo "--- журнал v3-real ---"
tail -10 "$LOG"
kill $SHIMPID 2>/dev/null
