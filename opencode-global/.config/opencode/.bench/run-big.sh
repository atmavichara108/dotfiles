#!/bin/zsh
# Бенч большого payload (796KB) через v3 к реальному апстриму.
cd /home/rudra/dotfiles/opencode-global/.config/opencode/shim
LOG=/tmp/opencode/jw/bench-big.log
: > "$LOG"
PORT=8786 UPSTREAM_BASE=https://api.justwoker.icu/v1 HANG_MS=90000 UPSTREAM_TIMEOUT_MS=600000 FORWARD_RETRIES=3 bun run justwoker-shim.ts > "$LOG" 2>&1 &
SHIMPID=$!
echo "bench-big pid=$SHIMPID"
sleep 3
curl -s -o /dev/null -w "health8786=%{http_code}\n" --max-time 5 http://127.0.0.1:8786/health
KEY=$(jq -r '.justwoker.key' ~/.local/share/opencode/auth.json)
HDR='-H x-api-key:$KEY -H anthropic-version:2023-06-01 -H content-type:application/json'
echo "--- (b) большой payload 796KB через v3 ---"
S=$(date +%s%N)
C=$(curl -s -o /tmp/opencode/jw/big-resp.json -w "http=%{http_code} t=%{time_total}s\n" --max-time 300 -X POST http://127.0.0.1:8786/v1/messages $HDR -d @/tmp/opencode/jw/big.json)
E=$(date +%s%N)
echo "$C"
echo "response-time=$(grep -oP 't=\K[0-9.]+' <<< "$C")"
echo "content_block_delta=$(grep -c content_block_delta /tmp/opencode/jw/big-resp.json 2>/dev/null || echo 0)"
echo "--- логи ---"
grep -E "hang|retry|content_block" "$LOG" | tail -10
kill $SHIMPID 2>/dev/null
