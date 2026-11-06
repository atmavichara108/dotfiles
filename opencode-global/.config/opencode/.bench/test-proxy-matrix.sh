#!/bin/zsh
# Проверка: напрямую (без прокси) vs через прокси — большое и малое тело.
KEY=$(jq -r '.justwoker.key' ~/.local/share/opencode/auth.json)

echo "=== 1. напрямую (noproxy), малое тело ==="
curl -s --noproxy '*' -o /dev/null -w "http=%{http_code} t=%{time_total}s\n" --max-time 20 \
  -X POST http://127.0.0.1:8787/v1/messages \
  -H "content-type: application/json" -H "x-api-key: $KEY" -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-opus-4-8","max_tokens":16,"stream":false,"messages":[{"role":"user","content":"hi"}]}'

echo "=== 2. напрямую к апстриму (noproxy), большое тело 796KB ==="
curl -s --noproxy '*' -o /dev/null -w "http=%{http_code} t=%{time_total}s\n" --max-time 45 \
  -X POST https://api.justwoker.icu/v1/messages \
  -H "content-type: application/json" -H "x-api-key: $KEY" -H "anthropic-version: 2023-06-01" \
  --data-binary @/tmp/opencode/jw/big.json

echo "=== 3. через прокси (env), большое тело 796KB ==="
curl -s -o /dev/null -w "http=%{http_code} t=%{time_total}s\n" --max-time 45 \
  -X POST https://api.justwoker.icu/v1/messages \
  -H "content-type: application/json" -H "x-api-key: $KEY" -H "anthropic-version: 2023-06-01" \
  --data-binary @/tmp/opencode/jw/big.json
