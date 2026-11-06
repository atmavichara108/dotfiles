#!/bin/zsh
# Прямой стрим через curl (через прокси env) к апстриму.
KEY=$(jq -r '.justwoker.key' ~/.local/share/opencode/auth.json)
echo "--- прямой stream:true, 60с ---"
curl -sN -o /tmp/opencode/jw/direct-stream.txt -w "http=%{http_code} t=%{time_total}s\n" \
  --max-time 60 -X POST https://api.justwoker.icu/v1/messages \
  -H "x-api-key: $KEY" -H "anthropic-version: 2023-06-01" -H "content-type: application/json" \
  -d '{"model":"claude-opus-4-8","max_tokens":32,"stream":true,"messages":[{"role":"user","content":"Скажи ровно: работает."}]}'
echo "--- размер ответа и события ---"
wc -c /tmp/opencode/jw/direct-stream.txt
grep -c "content_block" /tmp/opencode/jw/direct-stream.txt
head -c 400 /tmp/opencode/jw/direct-stream.txt
