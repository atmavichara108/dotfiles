# sddm-laptop-display — DisplayCommand для laptop-панели eDP-1-1

## Назначение

POSIX-sh скрипт, выполняемый SDDM как `DisplayCommand` перед показом greeter
(только для X11-сессий). Настраивает внутреннюю панель ноутбука (eDP-1-1)
как primary-дисплей: `--auto --primary --panning 0x0`. Отключает DP-3 только
если он присутствует и disconnected; если DP-3 connected — не трогает
mode/position/scale/primary.

Скрипт **никогда не выполняет** provider linking (NVIDIA-0 ↔ modesetting)
автоматически. Если eDP-1-1 не виден по live RandR-данным — логирует
providers/причину и завершается exit 0. Если eDP-1-1 connected — явно
логирует, что по текущим live RandR данным eDP уже виден через связанный
modesetting provider и linking не требуется.

**Не затрагивает:** Qtile, qtile.desktop, qtile-direct.desktop, SessionCommand,
user monitor-setup, Xorg.conf, EnvyControl, systemctl.

## Системные пути

| Файл | Путь в системе |
|------|----------------|
| Скрипт | `/usr/local/libexec/sddm-laptop-display` |
| Конфиг SDDM | `/etc/sddm.conf.d/20-laptop-display.conf` |

Установка создаёт **только** эти два файла — не более.

## Ручная установка

Выполнить один раз от root (или через sudo):

```sh
sudo install -m 0755 system-ops/sddm-laptop-display/sddm-laptop-display.sh \
    /usr/local/libexec/sddm-laptop-display

sudo install -m 0644 system-ops/sddm-laptop-display/20-laptop-display.conf \
    /etc/sddm.conf.d/20-laptop-display.conf
```

## Проверки установленных файлов

```sh
# Скрипт существует, исполняемый, принадлежит root
ls -l /usr/local/libexec/sddm-laptop-display
# Ожидается: -rwxr-xr-x root root ...

# Конфиг существует, читаемый
ls -l /etc/sddm.conf.d/20-laptop-display.conf
# Ожидается: -rw-r--r-- root root ...

# Синтаксис скрипта (POSIX sh)
sh -n /usr/local/libexec/sddm-laptop-display
```

## Проверка активной конфигурации до logout

Перед logout убедиться, что DisplayCommand будет подхвачен SDDM:

```sh
# Посмотреть effective config SDDM (без изменений системных файлов)
sddm --example-config 2>/dev/null | grep -A1 '^\[X11\]'
# Ожидается в выводе: DisplayCommand=/usr/local/libexec/sddm-laptop-display

# Альтернативно — проверить, что 20-laptop-display.conf читается
grep -r DisplayCommand /etc/sddm.conf.d/ /etc/sddm.conf 2>/dev/null
```

## Журнал

Все сообщения скрипта идут в systemd journal с тегом `sddm-laptop-display`:

```sh
journalctl -b -t sddm-laptop-display
```

## Rollback

Удалить **только** эти два установленных файла — не более:

```sh
sudo rm /usr/local/libexec/sddm-laptop-display
sudo rm /etc/sddm.conf.d/20-laptop-display.conf
```

После удаления SDDM вернётся к поведению по умолчанию (без DisplayCommand
или к значению из другого конфига). Перезапуск SDDM не требуется до
следующего logout/reboot.

## Что НЕ затрагивается

- **Qtile** (конфиг, сессия, виджеты) — без изменений
- **qtile.desktop** и **qtile-direct.desktop** — без изменений
- **SessionCommand** — без изменений
- **User monitor-setup** (пользовательские скрипты настройки мониторов) — без изменений
- **Xorg.conf**, **EnvyControl**, **systemctl** — без изменений

Скрипт работает исключительно в контексте SDDM DisplayCommand для X11 greeter
и влияет только на состояние X-сервера до показа greeter.

## Controlled test

**Важно:** исправление не считается доказанным до живого теста.

1. Установить файлы (см. «Ручная установка» выше)
2. До logout проверить активную конфигурацию через `sddm --example-config`
   или effective config — убедиться, что DisplayCommand подхватится
3. Logout из текущей сессии (не reboot — чтобы сохранить TTY для contingency)
4. На экране greeter SDDM убедиться, что изображение есть, разрешение нативное
5. Войти через **Qtile Direct** (не обычный Qtile, чтобы избежать конфликта
   с user monitor-setup)
6. Проверить журнал: `journalctl -b -t sddm-laptop-display`

## Contingency (чёрный greeter)

Если после logout greeter чёрный и изображение не видно:

1. Переключиться на TTY: `Ctrl+Alt+F2` (или F3/F4)
2. Залогиниться в TTY
3. Выполнить rollback — **две команды**:
   ```sh
   sudo rm /etc/sddm.conf.d/20-laptop-display.conf
   sudo rm /usr/local/libexec/sddm-laptop-display
   ```
4. Перезапустить SDDM:
   ```sh
   sudo systemctl restart sddm
   ```
5. Greeter должен вернуться к предыдущему поведению

Альтернативно, если TTY недоступен: reboot, при загрузке удалить файл
через live-USB или single-user mode.
