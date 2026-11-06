#!/bin/zsh
# Стрим-тест: stream:true через новый шим (curl-транспорт) к реальному апстриму.
cd /home/rudra/dotfiles/opencode-global/.config/opencode/shim
LOG=/tmp/opencode/jw/v3-stream.log
: > "$LOG"
PORT=8785 UPSTREAM_BASE=https://api.justwoker.icu/v1 bun run justwoker-shim.ts > "$LOG" 2>&1 &
SHIMPID=$!
sleep 3
KEY=$(jq -r '.justwoker.key' ~/.local/share/opencode/auth.json)
echo "--- stream:true через шим ---"
curl -sN -o /tmp/opencode/jw/v3-stream-resp.txt -w "http=%{http_code} t=%{time_total}s\n" \
  --max-time 120 -X POST http://127.0.0.1:8785/v1/messages \
  -H "x-api-key: $KEY" -H "anthropic-version: 2023-06-01" -H "content-type: application/json" \
  -d '{"model":"claude-opus-4-8","max_tokens":32,"stream":true,"messages":[{"role":"user","content":"Скажи ровно: работает. Без лишних слов."}]}'
echo "--- первые события SSE ---"
head -c 600 /tmp/opencode/jw/v3-stream-resp.txt
echo
echo "--- события с content_block ---"
grep -c "content_block" /tmp/opencode/jw/v3-stream-resp.txt
echo "--- журнал ---"
tail -5 "$LOG"
kill $SHIMPID 2>/dev/null
