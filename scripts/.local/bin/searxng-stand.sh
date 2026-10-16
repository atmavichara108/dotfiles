#!/usr/bin/env bash
# searxng-stand.sh — локальный SearXNG-стенд, вариант Docker (host-режим).
# Инструкция продукта: SSA/products/seo-outreach/docs/ops/searxng-stand.md
# Рабочая конфигурация зафиксирована вердиктом координатора 2026-10-16 (E2E 5/5):
#   --network host + GRANIAN_HOST/PORT в связке с server.bind_address 127.0.0.1 —
#   наружу не светит; bridge-вариант не работает (хост в интернет идёт через
#   локальные прокси, контейнер на bridge остаётся без сети и DNS).
# ПРОКСИ КОНТЕЙНЕРУ НЕ ДАВАТЬ общим списком env (вердикт координатора):
#   Яндекс-движку нужен прямой выход; пер-инжин proxy — опция outgoing.proxies
#   в settings.yml, отдельное решение не сегодня.
# Живой settings.yml с секретом хранится ВНЕ git в ~/searxng-stand.
# Идемпотентен: можно гонять повторно — не пересоздаёт конфиг, чинит контейнер.
set -euo pipefail

STAND_DIR="$HOME/searxng-stand"
IMAGE="searxng/searxng:latest"
NAME="searxng-stand"

command -v docker >/dev/null 2>&1 || { echo "docker не найден — установить (offering: sudo pacman -S docker, затем usermod -aG docker)" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "docker daemon недоступен этой сессии" >&2; exit 1; }

mkdir -p "$STAND_DIR/searxng"
if [ ! -f "$STAND_DIR/searxng/settings.yml" ]; then
  SECRET=$(openssl rand -hex 32)
  # Шаблон с placeholder-секретом: конкретный секрет генерится на месте и в git не попадает.
  cat > "$STAND_DIR/searxng/settings.yml" <<EOF
# SearXNG стенд (локальный, localhost-only) — создан searxng-stand.sh $(date -Is)
use_default_settings: true
server:
  secret_key: "$SECRET"
  bind_address: "127.0.0.1"
  port: 8888
  limiter: false
search:
  formats:
    - html
    - json
EOF
  echo "settings.yml создан: $STAND_DIR/searxng/settings.yml (секрет сгенерирован, вне git)"
else
  echo "settings.yml уже есть — не трогаю"
fi

if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "контейнер уже запущен"
elif docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  docker start "$NAME" >/dev/null
  echo "контейнер поднят из остановленного"
else
  docker run -d --name "$NAME" --restart unless-stopped \
    --network host \
    -e GRANIAN_HOST=127.0.0.1 -e GRANIAN_PORT=8888 \
    -v "$STAND_DIR/searxng:/etc/searxng" \
    "$IMAGE" >/dev/null
  echo "контейнер создан и запущен (host-режим, 127.0.0.1:8888)"
fi

sleep 5
docker ps --filter "name=$NAME" --format 'статус: {{.Status}} | {{.Names}} (host-режим, 127.0.0.1:8888)'
echo "версия образа: $(docker image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.version"}}' 2>/dev/null || docker image inspect "$IMAGE" --format '{{.Id}}')"
echo
echo "проверка (человек, один запрос):"
echo "  curl -s 'http://127.0.0.1:8888/search?q=test&format=json' | head -c 200"
echo "  (403 → json не в settings.yml или контейнер не перезапущен после правки)"
