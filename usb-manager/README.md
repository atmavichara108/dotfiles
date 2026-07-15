# USB Manager

GUI + CLI + Daemon для управления USB-накопителями.
Интеграция с Qtile, Dunst, Ranger.

## Установка

### Зависимости

```bash
sudo pacman -S python-gobject udisks2 libayatana-appindicator
pip install --user pyudev
```

### Stow

```bash
cd ~/dotfiles
stow usb-manager
```

### udev rule

```bash
sudo ln -sf ~/dotfiles/usb-manager/lib/udev/rules/99-usb-manager.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
```

### systemd (user service)

```bash
systemctl --user daemon-reload
systemctl --user enable --now usb-daemon
```

### Qtile (горячая клавиша)

Добавить в `~/.config/qtile/config.py`:

```python
Key([mod], "u", lazy.spawn("usb-cli toggle"), desc="Toggle USB Manager")
```

## Использование

### CLI

```bash
usb-cli list              # Список USB (JSON)
usb-cli mount /dev/sdb1   # Монтирование
usb-cli unmount /dev/sdb1 # Размонтирование
usb-cli eject /dev/sdb1   # Извлечение
usb-cli open /dev/sdb1    # Открыть в ranger
usb-cli toggle            # Показать/скрыть GUI
usb-cli status            # Статус демона
```

### GUI

- **Mod+u** — показать/скрыть окно
- **Tray icon** — клик: показать/скрыть, правый клик: меню
- При подключении USB — автоматическое уведомление и открытие окна

### Горячие клавиши в GUI

| Клавиша | Действие |
|---------|----------|
| Escape  | Закрыть окно (в трей) |

## Архитектура

```
~/.local/bin/usb-manager   — GUI (GTK3)
~/.local/bin/usb-daemon    — Демон (pyudev + DBus)
~/.local/bin/usb-cli       — CLI wrapper
~/.config/usb-manager/     — Конфиг
```

## Тестирование

```bash
# 1. Запуск демона
systemctl --user start usb-daemon
systemctl --user status usb-daemon

# 2. Подключение USB → уведомление + окно

# 3. CLI
usb-cli list
usb-cli mount /dev/sdb1
usb-cli open /dev/sdb1
usb-cli unmount /dev/sdb1

# 4. Mod+u → окно появляется/исчезает

# 5. Tray icon: клик → окно, правый клик → меню
```

## Troubleshooting

```bash
# Логи демона
journalctl --user -u usb-daemon -f

# Проверка DBus
gdbus introspect --session -d org.usbmanager.Daemon -o /org/usbmanager/Daemon

# Список USB через udisks2
gdbus introspect --system -d org.freedesktop.UDisks2 -o /org/freedesktop/UDisks2
```
