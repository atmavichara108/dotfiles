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
