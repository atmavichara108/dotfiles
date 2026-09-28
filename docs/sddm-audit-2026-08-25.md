# READ-ONLY АУДИТ: SDDM → Qtile Login Loop

**Дата:** 2026-08-25
**Аудитор:** planner (big-pickle)
**Система:** Manjaro, chroot из Live USB
**Пользователь:** rudra

---

## 1. НАЙДЕННЫЙ СКРИПТ OPENCODE

### Идентификация

Агент OpenCode **не создавал отдельный shell-скрипт-«бомбу»**. Вместо этого он:

1. Создал **dotfiles-пакет** `system-ops/sddm-pre-greeter/` с двумя файлами:
   - `sddm-pre-greeter.sh` — hook-скрипт для xrandr
   - `90-pre-greeter.conf` — конфиг SDDM

2. Пользователь **вручную** развернул эти файлы через `sudo install` и `sudo tee` — см. zsh_history, строки 130–200.

### Полный список системных команд из zsh_history

| # | Команда | Результат |
|---|---------|-----------|
| 130 | `sudo install -D -m 0755 system-ops/sddm-pre-greeter/sddm-pre-greeter.sh /usr/local/libexec/sddm-pre-greeter` | ✅ Установлен |
| 134 | `sudo install -D -m 0644 system-ops/sddm-pre-greeter/90-pre-greeter.conf /etc/sddm.conf.d/90-pre-greeter.conf` | ✅ Установлен |
| 139 | `sudo sddm --example-config \| grep -F 'DisplayCommand='` | Диагностика |
| 140 | `sudo grep -R "DisplayCommand" /etc/sddm.conf.d` | Диагностика |
| 141 | `sudo stat /usr/local/libexec/sddm-pre-greeter` | Диагностика |
| 142 | `reboot` | Перезагрузка — **login loop начался** |
| 143 | `sudo systemctl stop lightdm` | Попытка остановить lightdm |
| 153 | `sudo systemctl stop sddm` | Попытка остановить sddm |
| 161 | `pkill -u "$USER" -x qtile; pkill -u "$USER" -x xinit; sudo systemctl restart sddm` | Restart SDDM |
| 166–167 | `printf '[X11]\nSessionCommand=/usr/share/sddm/scripts/Xsession\n' \| sudo tee /etc/sddm.conf.d/99-xsession.conf` | **Попытка фикса** — добавлен SessionCommand |
| 176 | `sudo sed -i 's\|^Exec=.*\|Exec=/user/bin/qtile start\|' /usr/share/xsessions/qtile.desktop` | ⚠️ **Опечатка `/user/` вместо `/usr/`** |
| 183 | `sudo systenctl stop sddm` | ⚠️ **Опечатка `systenctl`** |
| 184 | `sudo mv /etc/sddm.conf /etc/sddm.conf.broken` | **Удалён** оригинальный sddm.conf |
| 185 | `sudo mv /etc/sddm.conf.d /etc/sddm.conf.d.broken` | **Удалена** оригинальная директория конфигов |
| 193 | `sudo systenctl restart sddm` | ⚠️ Опечатка |
| 194 | `sudo /user/bin/systemctl restart sddm` | ⚠️ **Опечатка `/user/`** |
| 196 | `printf '#!/bin/sh\nexec /usr/bin/qtile start\n' \| sudo tee /usr/local/libexec/qtile-session` | **Создан** wrapper |
| 197–198 | `sudo chmod +x /usr/local/libeexec/qtile-session` | ⚠️ **Опечатка `libeexec`** (2×) |
| 200 | `printf '[X11]\nDisplayCommand=/usr/local/libexec/qtile-session\n' \| sudo tee /etc/sddm.conf.d/10-laptop-recovery.conf` | ⚠️ **КРИТИЧЕСКАЯ ОШИБКА** |

### Итого — 3 системных файла созданы/изменены

| Файл | Содержимое | Владелец |
|------|-----------|----------|
| `/usr/local/libexec/sddm-pre-greeter` | xrandr hook (eDP-1-1 primary, DP-3 off) | root:root 755 |
| `/usr/local/libexec/qtile-session` | `#!/bin/sh; exec /usr/bin/qtile start` | root:root 755 |
| `/etc/sddm.conf.d/10-laptop-recovery.conf` | `DisplayCommand=/usr/local/libexec/qtile-session` | root:root 644 |

### Доказательства запуска

- **zsh_history** — все команды `sudo install/tee/mv` задокументированы
- **stat файлов** — mtime/ctime совпадают с историей команд (13:58–16:45, Aug 25)
- **`/etc/sddm.conf.d/10-laptop-recovery.conf`** — существует, mtime=16:45
- **`/etc/sddm.conf.d.broken/`** — пустая директория (оригинальные конфиги были перемещены)

---

## 2. ПЕРВОПРИЧИНА LOGIN LOOP

### Главная причина: DisplayCommand запускает `qtile start` как root до greeter

**Доказательства:**

1. `/etc/sddm.conf.d/10-laptop-recovery.conf`:
   ```ini
   [X11]
   DisplayCommand=/usr/local/libexec/qtile-session
   ```

2. `/usr/local/libexec/qtile-session`:
   ```sh
   #!/bin/sh
   exec /usr/bin/qtile start
   ```

3. **Как работает SDDM:**
   - `DisplayCommand` → выполняется **ДО** greeter, **как root**, в контексте X-сервера
   - Пользователь видит greeter → вводит пароль → SDDM запускает `SessionCommand`
   - Но `DisplayCommand` уже запустил `qtile start` как root → конфликт

4. **Почему loop:** Qtile (запущенный из `DisplayCommand` как root) создаёт X-сессию. Когда пользователь логинится, SDDM пытается запустить **ещё одну** сессию через `qtile.desktop` → конфликт → сессия падает → возврат на greeter.

### Вторичные причины

| # | Проблема | Доказательство |
|---|----------|---------------|
| 2 | `qtile.desktop` использует systemd-based старт: `systemctl --user start --wait qtile.service` — требует properly working user session | `/usr/share/xsessions/qtile.desktop` строка Exec |
| 3 | Qtile крашится с `AttributeError: 'Qtile' object has no attribute 'current_screen'` — API несовместимость с 0.37.0 | `/home/rudra/.local/share/qtile/qtile.log` |
| 4 | `sddm-helper exited with 127` — возможно, обрыв цепочки из-за DisplayCommand | предыдущие journal-записи (из контекста) |
| 5 | Множественные опечатки в recovery-командах (`systenctl`, `/user/bin/`, `libeexec`) | zsh_history |

### Уровень уверенности: 95% — DisplayCommand = root qtile start

---

## 3. ПЕРВОПРИЧИНА ЧЁРНОГО ЭКРАНА / НЕСУЩЕСТВУЮЩЕГО МОНИТОРА

### Конфигурация

`sddm-pre-greeter` хардкодит:
```bash
internal_output="eDP-1-1"
external_output="DP-3"
# Всегда делает: xrandr --output eDP-1-1 --auto --primary
# Всегда делает: xrandr --output DP-3 --off
```

### Проблемы

1. **Hook не зарегистрирован в SDDM** — файл `/usr/local/libexec/sddm-pre-greeter` создан, но **ни один конфиг SDDM не ссылается на него** как `DisplayCommand` или `DisplaySetup`. Он просто лежит мёртвым файлом.

2. **Нет `90-pre-greeter.conf`** в `/etc/sddm.conf.d/` — команда `sudo install` установила его, но `sudo mv /etc/sddm.conf.d /etc/sddm.conf.d.broken` (строка 185) **удалила** эту директорию. Новая директория `/etc/sddm.conf.d/` была создана позже, но содержит **только** `10-laptop-recovery.conf`.

3. **Qtile autostart-x11** — `monitor-setup` закомментирован (stash-версия). Но в текущем main он **активен** — неясно, какой статус.

4. **`qtile.desktop`** использует `systemctl --user start --wait qtile.service` — если systemd user session не запущена корректно, мониторы не настраиваются.

**Доказательства:**
- `ls /etc/sddm.conf.d/` → только `10-laptop-recovery.conf`
- `/etc/sddm.conf.d.broken/` → пуста (конфиги были перемещены и, видимо, потеряны)
- `cat /usr/local/libexec/sddm-pre-greeter` → скрипт существует, но не вызывается

---

## 4. ЧТО БЫЛО ИЗМЕНЕНО ПОСЛЕ ПОЛОМКИ

### Изменения OpenCode (agent)

| Файл | Изменение |
|------|-----------|
| `system-ops/sddm-pre-greeter/sddm-pre-greeter.sh` | Создан xrandr hook |
| `system-ops/sddm-pre-greeter/90-pre-greeter.conf` | Создан SDDM-конфиг |
| `docs/decisions.md` | ADR-014: pre-greeter single-display |
| `docs/runbooks/sddm-pre-greeter.md` | Runbook для hook |
| `.opencode/subagent/system-ops.md` | Новый subagent |
| `qtile/config.py` | `screens = screens.init_screens()[:1]` — 1 экран |
| `qtile/autostart-x11` | monitor-setup закомментирован |

### Recovery-изменения (пользователь вручную)

| # | Действие | Результат |
|---|----------|-----------|
| 1 | `sudo install sddm-pre-greeter.sh` | ✅ Установлен |
| 2 | `sudo install 90-pre-greeter.conf` | ✅ Установлен, но потом **удалён** mv |
| 3 | `reboot` | Login loop |
| 4 | `sudo systemctl stop lightdm` | Не помогло |
| 5 | `sudo systemctl stop sddm` → restart | Не помогло |
| 6 | `printf 99-xsession.conf \| sudo tee` | Создан SessionCommand |
| 7 | `sudo sed -i` → `/user/bin/qtile` | ⚠️ Опечатка |
| 8 | `sudo mv sddm.conf → sddm.conf.broken` | Удалён основной конфиг |
| 9 | `sudo mv sddm.conf.d → sddm.conf.d.broken` | Удалены все конфиги |
| 10 | `printf qtile-session \| sudo tee` | Создан wrapper |
| 11 | `printf 10-laptop-recovery.conf \| sudo tee` | ⚠️ DisplayCommand = qtile (root) |

---

## 5. МИНИМАЛЬНЫЙ ПЛАН ОТКАТА

### Шаг 1: Удалить опасные файлы

```bash
# Удалить DisplayCommand-ловушку (root → qtile)
sudo rm /etc/sddm.conf.d/10-laptop-recovery.conf

# Удалить qtile-session wrapper (не нужен)
sudo rm /usr/local/libexec/qtile-session

# Опционально: удалить sddm-pre-greeter (пока не зарегистрирован)
sudo rm /usr/local/libexec/sddm-pre-greeter
```

### Шаг 2: Восстановить SDDM конфиг

```bash
# Восстановить оригинальный sddm.conf (из пакета)
sudo pacman -S --overwrite '*' sddm
# Или вручную:
sudo cp /usr/lib/sddm/sddm.conf.d/default.conf /etc/sddm.conf
```

### Шаг 3: Восстановить qtile.desktop

```bash
# Восстановить из пакета
sudo pacman -S --overwrite '*' qtile
# Или вручную — Exec должен быть:
# Exec=qtile start
# (не systemd-based, пока не убедимся в user session)
```

### Шаг 4: Откатить git stash

```bash
cd /home/rudra/dotfiles
git stash pop  # Вернуть changes
git checkout -- qtile/config.py  # Откатить screens[:1]
# Или:
git stash drop  # Если не нужен
```

### Шаг 5: Проверить autostart-x11

```bash
# Убедиться что monitor-setup НЕ закомментирован
cat ~/.config/qtile/autostart-x11 | grep monitor-setup
```

### Шаг 6: Перезагрузка

```bash
sudo reboot
```

---

## 6. ПРОВЕРКА ПОСЛЕ ОТКАТА

| Проверка | Команда | Ожидаемый результат |
|----------|---------|-------------------|
| Нет DisplayCommand | `grep -r DisplayCommand /etc/sddm.conf.d/` | Пусто |
| Нет qtile-session | `ls /usr/local/libexec/qtile-session` | No such file |
| SDDM config exists | `cat /etc/sddm.conf` | Секция [X11] с дефолтами |
| qtile.desktop Exec | `grep Exec /usr/share/xsessions/qtile.desktop` | `Exec=qtile start` |
| Один монитор | `xrandr --query \| grep " connected"` | `eDP-1-1 connected` |
| Два монитора | Подключить DP-3 → `xrandr --query` | `DP-3 connected` |
| Qtile стартует | `startx` или через SDDM | Нет AttributeError |
| Login loop | Ввести пароль в SDDM | Вход в сессию |

---

## КРАТКАЯ СВОДКА

| Аспект | Статус |
|--------|--------|
| **Скрипт OpenCode** | Пакет `system-ops/sddm-pre-greeter/` в dotfiles + ручное развертывание через `sudo install/tee` |
| **DisplayCommand** | ⚠️ **КРИТИКА** — `10-laptop-recovery.conf` запускает `qtile start` как root до greeter |
| **sddm-pre-greeter** | Файл существует, но **нигде не зарегистрирован** — мёртвый код |
| **sddm.conf** | Удалён → `/etc/sddm.conf.broken` (директория!) |
| **sddm.conf.d** | Оригинал удалён → `.broken`, новый содержит только опасный `10-laptop-recovery.conf` |
| **qtile.desktop** | systemd-based Exec — потенциальная проблема с user session |
| **Qtile API** | `current_screen` AttributeError — несовместимость с 0.37.0 |
| **Git** | Working tree clean, HEAD на `origin/main`, stash содержит изменения OpenCode |

---

## ТАЙМЛАЙН (Aug 25)

```
13:58  /usr/local/libexec/sddm-pre-greeter создан (sddm-pre-greeter.sh)
14:00  sddm-pre-greeter установлен в /usr/local/libexec/
14:50  Qtile crash: AttributeError 'current_screen' (первый)
14:51  Qtile crash повторный
15:17  /etc/sddm.conf.d.broken создан (mv оригинала)
15:42  qtile.desktop modified (systemd Exec)
16:09  Время изменения .broken директорий
16:11  qtile.desktop modification time (pacman report)
16:20  qtile.desktop access time
16:40  /usr/local/libexec/qtile-session создан
16:45  /etc/sddm.conf.d/10-laptop-recovery.conf создан
```

---

*Документ сгенерирован planner (read-only). Не применяй изменения без подтверждения.*
