# Qtile Direct — recovery session

Альтернативный `.desktop`-файл для SDDM, запускающий Qtile напрямую
(`/usr/bin/qtile start`), без systemd user service. Нужен как запасной
вход, когда основной `qtile.desktop` от пакета сломан или когда
systemd-user-сервис не стартует.

## Установка

```bash
sudo install -Dm0644 \
  system-ops/qtile-direct/qtile-direct.desktop \
  /usr/share/xsessions/qtile-direct.desktop
```

## Проверка

```bash
cat /usr/share/xsessions/qtile-direct.desktop
grep '^Exec=' /usr/share/xsessions/qtile-direct.desktop
```

## Удаление/откат

```bash
sudo rm -f /usr/share/xsessions/qtile-direct.desktop
```

## Пояснения

- **Не заменяет пакетный `qtile.desktop`** — живёт рядом, отдельным файлом
  `qtile-direct.desktop`. Пакетный `.desktop` остаётся нетронутым.
- **Обновление qtile его не перезаписывает** — файл устанавливается вручную
  через `install` в `/usr/share/xsessions/`, pacman о нём не знает и при
  обновлении пакета `qtile` не трогает.
- **Запускает `/usr/bin/qtile start` напрямую** — `Exec=` указывает на
  абсолютный путь бинарника с подкомандой `start`, без обёрток, без
  `dbus-launch`, без systemd user service.
- **После установки**: выйти из текущей сессии, в SDDM выбрать сеанс
  «Qtile Direct» и войти.
- **До обновления системы** проверить, что текущая версия Qtile — 0.36
  (или новее) и `/usr/bin/qtile start` работает:
  ```bash
  qtile --version
  /usr/bin/qtile start  # в отдельном tty, для проверки
  ```
