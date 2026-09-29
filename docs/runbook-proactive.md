---
type: Runbook
title: Проактивная программа — ранбук
description: Гайды по контурам P0–P2: устройство, пользование, диагностика.
timestamp: 2026-09-29
status: active
---

# Ранбук проактивной программы

> Каждый контур: что это → как пользоваться → как чинить. Правила общие:
> тишина при OK, алерт только на переходах, `unknown` вместо вранья OK.

## P0 — prod-healthcheck (наблюдатель локальных сервисов)

### Что это
Systemd-таймер каждые 2 мин дёргает HTTP-цели из `targets.conf`
(pipboy + termproxy-порты). Порог 3 подряд провала гасит ложные алерты
при рестартах. Счётчики — `~/.local/share/prod-healthcheck/*.fail`.

### Файлы
- `scripts/.local/bin/prod-healthcheck` — oneshot-скрипт (100755 в git)
- `scripts/.config/prod-healthcheck/targets.conf` — цели `name url`
- `environment.d/.config/systemd/user/prod-healthcheck.{service,timer}`

### Пользование
```bash
# ручной прогон
prod-healthcheck; echo $?
# счётчики (0 = ok, растёт = деградация)
cat ~/.local/share/prod-healthcheck/*.fail
# включить таймер (после stow)
systemctl --user daemon-reload
systemctl --user enable --now prod-healthcheck.timer
# статус
systemctl --user status prod-healthcheck.timer
journalctl --user -u prod-healthcheck.service -n 20
```

### Цели
Редактируй `~/.config/prod-healthcheck/targets.conf` (симлинк в репо):
`pipboy`, `termproxy-<проект>`. termproxy-порты плавают между сессиями —
сверяй с `ss -tlnp`. Прод-URL — только после утверждения критериев (P1).

### Диагностика
- Нет алертов вообще → проверь `notify-send` и что таймер enabled.
- Вечный down одной цели → сверь порт (`ss -tlnp | grep <порт>`), поправь
  `targets.conf` или подними сервис.
- Сбросить счётчик вручную: `echo 0 > ~/.local/share/prod-healthcheck/<name>.fail`.

### Адаптивность (заложена)
- Порог N=3 — нагрузочная (ложные срабатывания при рестартах).
- Балансная — нечего тратить (локальный curl), см. P1 для платных проб.
- mcode — контур клиент-независим (юнит уровня systemd, не плагин);
  mcode-паритет достигается shared targets.conf (TD-001 отдельно).

## P1 — notify-push (пуш с контекстом)

### Что это
Sink-адаптер `scripts/.local/bin/notify-push`: есть `TELEGRAM_BOT_TOKEN` +
`TELEGRAM_CHAT_ID` в окружении → Telegram Bot API, иначе фолбэк на локальный
`notify-send`. prod-healthcheck зовёт его вместо прямого notify-send.
Критические алерты идут без silent, восстановления — low.

### Файлы
- `scripts/.local/bin/notify-push` (100755 в git)
- `environment.d/.../prod-healthcheck.service` — `EnvironmentFile=-.../push.env`
  (дефис: без файла юнит не падает)

### Пользование (настройка Telegram — руками, секреты только у тебя)
```bash
# 1. Создай бота через @BotFather, узнай chat_id (@userinfobot)
# 2. Положи секреты (0600, вне репо):
install -m 600 /dev/null ~/.config/push/push.env
printf 'TELEGRAM_BOT_TOKEN=...\nTELEGRAM_CHAT_ID=...\n' >> ~/.config/push/push.env
# 3. Перечитай юнит и проверь тестовым алертом:
systemctl --user daemon-reload
notify-push "P1-тест" "проверка пуша" "low"
```

### Диагностика
- Пуш не приходит → `journalctl --user -u prod-healthcheck.service` + проверь
  токен прямым curl (токен в командной строке светить нельзя — только env).
- Без push.env всё работает локально — это штатный режим, не ошибка.
