#!/bin/bash
# git-prune-branches — демон чистки смерженных task-веток (dotfiles + Vault).
# Запуск: systemd user timer git-prune.timer (еженедельно).
# Безопасность: только task/*, только полностью влитые в main, только старше
# 7 дней; никогда текущую, никогда main/master, backup/*, feat/*, mcode/*,
# temp/*, snapshot/*, review/* и невлитые. Удаление только через `branch -d`
# (невлитое он откажется удалять — второй замок).
set -euo pipefail

MAX_AGE_DAYS=7
REPOS=("$HOME/dotfiles" "$HOME/Projects/OpenCode-Vault")

die() { echo "Error: $*" >&2; exit 1; }
log() { echo "[$(date +%H:%M:%S)] $*"; }

prune_repo() {
  local repo="$1"
  [ -d "$repo/.git" ] || { log "skip $repo: не git-репо"; return 0; }
  log "== $repo =="
  git -C "$repo" fetch origin --prune 2>/dev/null || log "fetch пропущен (офлайн?)"
  local now current cutoff branch ts
  now=$(date +%s)
  current=$(git -C "$repo" branch --show-current)
  cutoff=$((now - MAX_AGE_DAYS * 86400))
  git -C "$repo" branch --format='%(refname:short) %(committerdate:unix)' | while read -r branch ts; do
    case "$branch" in
      task/*) ;;
      *) continue ;;
    esac
    [ "$branch" = "$current" ] && continue
    [ "$ts" -ge "$cutoff" ] && continue
    if git -C "$repo" branch --merged main --format='%(refname:short)' | grep -qx "$branch"; then
      log "удаляю $branch (влита, старше 7д)"
      git -C "$repo" branch -d "$branch"
    fi
  done
}

for repo in "${REPOS[@]}"; do
  prune_repo "$repo"
done
log "готово"
