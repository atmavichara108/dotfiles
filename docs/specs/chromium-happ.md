# Chromium HAPP Integration Spec

## Цель

Обычный Chromium всегда запускается через единый HAPP-aware wrapper, который автоматически выбирает прокси на основе режима proxyctl.

## Требования

### Wrapper (`scripts/.local/bin/chromium-happ`)

- Читает режим из `~/.config/proxyctl/mode`
- Поддерживает режимы:
  - `happ` → `socks5://127.0.0.1:10808`
  - `tor` → `socks5://127.0.0.1:9050`
  - `off` → direct (без прокси)
  - `auto` → проверяет порт 10808, если активен → happ, иначе → tor
- Сохраняет все аргументы командной строки
- Использует `exec` для замены процесса

### Qtile Hotkeys

- `Super+G` → `chromium-happ` (новый, HAPP-aware)
- `Super+Shift+G` → Genspark via Tor (сохранить без изменений)
- `Super+Shift+W` → `google-chrome-proxy` (не трогать, это Google Chrome, не Chromium)

### Desktop Entry (`xdg/.local/share/applications/chromium.desktop`)

- `Exec=chromium-happ %U`
- MIME types: `text/html`, `application/xhtml+xml`, `x-scheme-handler/http`, `x-scheme-handler/https`
- Заменяет существующий `chromium.desktop` в `~/.local/share/applications/`

### Ranger Integration

- `ranger/.config/ranger/rifle.conf` line 74: `chromium` → `chromium-happ`
- Обеспечивает, что открытие HTML файлов в Ranger идёт через wrapper

### Не трогать

- Tor web-apps: `genspark-tor.desktop`, `chromium-tor.desktop`, `youtube-tor.desktop`, `chrome-tor.desktop`
- `create-tor-webapp` script
- `google-chrome-proxy` (это Google Chrome, не Chromium)
- `/etc`, системные настройки
- Установка пакетов

## Proxy Modes (из proxyctl)

```
happ: socks5h://127.0.0.1:10808 (HAPP proxy, DNS через прокси)
tor:  socks5://127.0.0.1:9050   (Tor fallback)
off:  (очищено)
auto: проверяет порт 10808, если активен → happ, иначе → tor
```

**Примечание:** Wrapper использует `socks5://` (не `socks5h://`) для HAPP, как указано в требованиях.

## DoD (Definition of Done)

- [x] `bash -n scripts/.local/bin/chromium-happ` — синтаксис валиден
- [x] `desktop-file-validate xdg/.local/share/applications/chromium.desktop` — валиден
- [x] `stow -n scripts` — без конфликтов
- [x] `stow -n xdg` — без конфликтов
- [x] Qtile hotkey `Super+G` добавлен
- [x] Ranger rifle.conf обновлён
- [x] Документация обновлена
- [x] Wrapper читает `~/.config/proxyctl/mode`
- [x] Wrapper поддерживает режимы: happ, tor, off, auto
- [x] Wrapper использует `exec` и сохраняет все аргументы
- [x] Wrapper исполняемый (755)
- [x] Ranger: chromium-happ перед chromium-browser (нет обхода)
- [x] environment.d/proxy.conf откатен (вне-scope изменения)

## Files Changed

1. `docs/specs/chromium-happ.md` — spec (source of truth)
2. `scripts/.local/bin/chromium-happ` — wrapper
3. `qtile/.config/qtile/keys.py` — Super+G hotkey
4. `xdg/.local/share/applications/chromium.desktop` — desktop entry
5. `ranger/.config/ranger/rifle.conf` — HTML opener

## Testing

После stow:
```bash
# Проверить симлинки
ls -la ~/.local/bin/chromium-happ
ls -la ~/.local/share/applications/chromium.desktop

# Проверить wrapper
chromium-happ --version
chromium-happ https://example.com

# Проверить режимы
echo "happ" > ~/.config/proxyctl/mode
chromium-happ --proxy-server  # должно использовать socks5://127.0.0.1:10808

echo "tor" > ~/.config/proxyctl/mode
chromium-happ --proxy-server  # должно использовать socks5://127.0.0.1:9050

echo "off" > ~/.config/proxyctl/mode
chromium-happ --proxy-server  # должно быть direct

echo "auto" > ~/.config/proxyctl/mode
chromium-happ --proxy-server  # должно проверить порт 10808
```
