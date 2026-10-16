#!/usr/bin/env bash
# sync-mcode-config.sh — доставка SSOT конфига mcode: dotfiles → зона движка.
# Направление канонческое (docs/specs/mcode-coexistence.md §2.2): dotfiles → движок,
# никогда наоборот. Идемпотентен; живой прогон только при diff != ∅.
# Kill-criterion (спека §5 D2):
#   (а) diff удаляет из цели строки с ключами/секретами, коих нет в источнике → СТОП;
#   (б) движок после синка не стартует → восстановить .bak (руками, скрипт бэкапит);
#   (в) движок читает НЕ тот файл → разовый подтверждающий зонд источника
#       чтения (lsof/strace по живому процессу), результат — в docs/engines.md.
# Опции: --dry-run (по умолчанию только diff без записи), --apply (запись с .bak).
set -euo pipefail

SRC="$HOME/dotfiles/opencode-global/.config/opencode/mcode.jsonc"
DST="$HOME/.local/share/m-code-data/config/mcode.jsonc"
MODE="${1:---dry-run}"

[[ -f "$SRC" ]] || { echo "СТОП: SSOT-источник не найден: $SRC" >&2; exit 1; }
[[ -d "$(dirname "$DST")" ]] || { echo "СТОП: зона mcode не смонтирована: $(dirname "$DST") (mcode не установлен?)" >&2; exit 1; }

DIFF="$(diff -u "$DST" "$SRC" || true)"
if [[ -z "$DIFF" ]]; then
  echo "синх: цель идентична SSOT — ничего не делаем"
  exit 0
fi

echo "=== diff цель → SSOT (+ = станет) ==="
echo "$DIFF" | head -60
echo "=== всего изменённых строк: $(echo "$DIFF" | grep -cE '^[+-][^+-]' || true) ==="

# Гвард секретов: удаляемые из цели key/secret-строки, отсутствующие в источнике.
REMOVED_SECRETS="$(echo "$DIFF" | grep -E '^-' | grep -vE '^-{3}' \
  | grep -iE '(api[_-]?key|apikey|token|secret|password)' || true)"
if [[ -n "$REMOVED_SECRETS" ]]; then
  while IFS= read -r line; do
    bare="${line#-}"
    if ! grep -Fq -- "$bare" "$SRC"; then
      echo "СТОП (kill-criterion а): цель содержит секретную строку, которой нет в SSOT:" >&2
      echo "  ${bare:0:80}…" >&2
      echo "Перенеси значение в SSOT или храни в secret-service mcode; повторить без — нельзя." >&2
      exit 2
    fi
  done <<< "$REMOVED_SECRETS"
fi

if [[ "$MODE" == "--dry-run" ]]; then
  echo "dry-run: запись не производилась (передать --apply)"
  exit 0
fi
[[ "$MODE" == "--apply" ]] || { echo "неизвестный режим: $MODE (ожидалось --dry-run|--apply)" >&2; exit 1; }

BAK="${DST}.bak.$(date -u +%Y%m%dT%H%M%SZ)"
cp -p "$DST" "$BAK"
cp "$SRC" "$DST"
echo "синхронизировано: $DST (бэкап: $BAK)"
echo "проверь старт mcode; при сбое: cp '$BAK' '$DST'"
