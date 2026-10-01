#!/bin/bash
# install-githooks.sh — поставить pre-commit gate dotfiles в указанный репозиторий.
# Единая истина обоих SDK: хук срабатывает из opencode, mcode и терминала одинаково.
# Использование: ./scripts/install-githooks.sh [--repo DIR]  (default: cwd)
# Идемпотентно: существующий pre-commit бэкапится в pre-commit.bak-<дата>.
set -u

REPO="."
if [ "${1:-}" = "--repo" ] && [ -n "${2:-}" ]; then REPO="$2"; fi

HOOK_SRC="$HOME/dotfiles/githooks/pre-commit"
HOOK_DST="$REPO/.git/hooks/pre-commit"

[ -d "$REPO/.git" ] || { echo "❌ $REPO — не git-репозиторий" >&2; exit 1; }
[ -f "$HOOK_SRC" ] || { echo "❌ нет канона: $HOOK_SRC" >&2; exit 1; }

if [ -e "$HOOK_DST" ] && [ ! -L "$HOOK_DST" ]; then
  cp "$HOOK_DST" "$HOOK_DST.bak-$(date +%F)" && echo "бэкап: $HOOK_DST.bak-$(date +%F)"
fi
ln -sf "$HOOK_SRC" "$HOOK_DST"
echo "✅ pre-commit → $HOOK_SRC (репо: $REPO)"
