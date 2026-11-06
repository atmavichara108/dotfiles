#!/bin/zsh
# Бенч шима v3 против управляемых заглушек (stub.mjs на 8791).
cd /home/rudra/dotfiles/opencode-global/.config/opencode/shim
LOG=/tmp/opencode/jw/bench-shim.log
: > "$LOG"
PORT=8785 UPSTREAM_BASE=http://127.0.0.1:8791/v1 HANG_MS=5000 UPSTREAM_TIMEOUT_MS=30000 FORWARD_RETRIES=3 \
  bun run justwoker-shim.ts > "$LOG" 2>&1 &
SHIMPID=$!
echo "bench-shim pid=$SHIMPID"
sleep 3
curl -s -o /dev/null -w "health8785=%{http_code}\n" --max-time 5 http://127.0.0.1:8785/health

req() { # $1=маркер в теле
  curl -sN --max-time 30 -X POST http://127.0.0.1:8785/v1/messages \
    -H "x-api-key: test" -H "anthropic-version: 2023-06-01" -H "content-type: application/json" \
    -d "{\"model\":\"claude-opus-4-8\",\"max_tokens\":32,\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"$1\"}]}"
}

echo "--- (a) live stream ---"
S=$(date +%s%N)
A=$(req "live test" | grep -c "content_block_delta")
E=$(date +%s%N)
echo "content_block_delta=$A время_ms=$(( (E - S) / 1000000 ))"

echo "--- (c) hang-retry (stub молчит 8s на 1-м запросе, watchdog 5s) ---"
S=$(date +%s%N)
C=$(req "hangtest please" | grep -c "content_block_delta")
E=$(date +%s%N)
echo "content_block_delta=$C время_ms=$(( (E - S) / 1000000 )) (ожидаем ~5500)"

echo "--- (d) fallback (регрессия: стрим без content_block) ---"
S=$(date +%s%N)
D=$(req "regresstest please" | grep -c "content_block_delta")
E=$(date +%s%N)
echo "content_block_delta=$D время_ms=$(( (E - S) / 1000000 ))"

echo "--- логи бенч-шима ---"
grep -E "hang|fallback|retry" "$LOG" | tail -8
kill $SHIMPID 2>/dev/null
