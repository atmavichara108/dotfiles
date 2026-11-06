#!/bin/bash
# apply.sh — применение SSH-hardening (мандат ЦУ ic-ssh-harden).
# Запуск: от root (sudo). Откат: rollback.sh. Перед применением проверяет,
# что ключ доступа есть (не запираем), валидирует конфиг и делает бэкап.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)/10-hardening.conf"
DST="/etc/ssh/sshd_config.d/10-hardening.conf"
BAK="/etc/ssh/sshd_config.d/10-hardening.conf.bak.$(date +%Y%m%d-%H%M%S)"

# 0. Предусловие: ключ доступа существует, иначе останов (kill-условие цели).
KEY=/home/rudra/.ssh/authorized_keys
if [ ! -s "$KEY" ]; then
  echo "❌ STOP: $KEY пуст или отсутствует — ключ-only запирает доступ. Сначала ключ." >&2
  exit 1
fi
echo "✅ предусловие: ключ доступа на месте ($(wc -l < "$KEY") шт.)"

# 1. Бэкап прежнего состояния (откат проверяем).
if [ -f "$DST" ]; then
  cp -a "$DST" "$BAK"
  echo "✅ бэкап: $BAK"
else
  echo "✅ прежнего drop-ина нет — откат = удаление файла (rollback.sh)"
fi

# 2. Применение.
cp "$SRC" "$DST"
chmod 644 "$DST"

# 3. Валидация перед reload — битый конфиг не должен положить доступ.
if ! sshd -t; then
  echo "❌ sshd -t: конфиг невалиден — откат автоматический" >&2
  rm -f "$DST"
  sshd -t && echo "✅ откат к прежнему состоянию выполнен" || echo "❌ откат тоже невалиден — зови владельца" >&2
  exit 2
fi
echo "✅ sshd -t: конфиг валиден"

# 4. Перезапуск sshd под управлением systemd (служба уже активна — только reload).
systemctl reload sshd || systemctl restart sshd
echo "✅ sshd перезапущен"

# 5. Проверка DoD: парольный вход выключен явно, корень-off.
echo "--- эффективные настройки ---"
sshd -T | grep -iE "^(passwordauthentication|permitrootlogin|kbdinteractiveauthentication|maxauthtries)"
echo "--- попытка парольного входа (ожидаем отказ) ---"
if ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no \
       -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
       -o BatchMode=yes rudra@127.0.0.1 true 2>&1 | grep -q "Permission denied"; then
  echo "✅ парольный вход отклонён"
else
  echo "❌ парольный вход НЕ отклонён — немедленно rollback.sh" >&2
  exit 3
fi
echo "--- listener'ы (снимок) ---"
ss -tln | grep -E ":22\b"
echo "🎉 hardening применен"
