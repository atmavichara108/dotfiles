#!/bin/bash
# rollback.sh — откат SSH-hardening к прежнему состоянию (мандат ЦУ ic-ssh-harden).
# Удаляет drop-ин, валидирует и перезапускает sshd. Прежний конфиг сохраняется
# копией с меткой времени (apply.sh её делает); если копий нет — прежнее
# состояние и есть «по умолчанию» (drop-ина не было до меры).
set -euo pipefail

DST="/etc/ssh/sshd_config.d/10-hardening.conf"

if [ -f "$DST" ]; then
  LATEST="$(ls -1t /etc/ssh/sshd_config.d/10-hardening.conf.bak.* 2>/dev/null | head -1 || true)"
  if [ -n "${LATEST:-}" ]; then
    RESTORED="$LATEST.restored.$(date +%Y%m%d-%H%M%S)"
    cp -a "$LATEST" "$RESTORED"
    echo "✅ прежний drop-in сохранён копией: $RESTORED"
  fi
  rm -f "$DST"
  echo "✅ drop-ин удалён"
else
  echo "✅ drop-ина и нет — откатывать нечего"
fi

sshd -t
systemctl reload sshd || systemctl restart sshd
echo "✅ sshd перезапущен, состояние — прежнее"
sshd -T | grep -iE "^(passwordauthentication|permitrootlogin)" || true
echo "🎉 откат выполнен"
