---
type: Execution Spec
title: Pip-Boy хоткей (dotfiles / qtile)
project: dotfiles
status: proposed
timestamp: 2026-09-16
related: "[[03-Projects/vault]]"
---

# Pip-Boy хоткей

## Цель

Один глобальный хоткей открывает Pip-Boy (v10 tiling multiplexer) из любого
места — не через rofi-меню, а напрямую клавишей.

## Контекст

- Pip-Boy уже имеет on-demand host (`tools/ecosystem-map/pipboy.py`) и
  rofi-фронтенд `/home/rudra/.local/bin/pipboy-rofi` с действием `open`
  (поднимает host при простое + открывает браузер на `http://127.0.0.1:8123/`).
- Тот же URL работает в GUI-браузере, TUI-браузере и смартфоне (LAN).
- Хост сам гасится через 1800s простоя — держать его «навсегда» не нужно.

## Решение

Забиндить хоткей в qtile (`~/.config/qtile/config.py`, раздел `keys`),
вызывающий существующий `pipboy-rofi open`:

```python
from libqtile.config import Key
from libqtile.lazy import lazy

Key(["mod4"], "p", lazy.spawn("pipboy-rofi open"), desc="Pip-Boy"),
```

- `mod4` = Super/Win; клавиша `p` свободна в стандартной раскладке qtile.
- `pipboy-rofi open` идемпотентен: если host поднят — просто откроет браузер,
  если нет — поднимет и откроет. Никакой новой логики писать не надо.
- Спawn применяется через GNU Stow (пакет `qtile` уже управляется Stow).

## Вариант на выбор (при конфликте клавиши)

| Клавиша | Замечание |
|---|---|
| `mod4 + p` | предпочтительно (Pip-Boy → p) |
| `mod4 + b` | если `p` занята менеджером паролей/другое |

## DoD

- [ ] Хоткей добавлен в `qtile/config.py` keys.
- [ ] `qtile cmd-obj -o cmd -f restart` (или `qtile shell` → `restart`) — конфиг без ошибок.
- [ ] Нажатие `mod4 + p` открывает Pip-Boy в браузере; повторное — не плодит вкладки.
- [ ] `pipboy-rofi open` вызывается без ручного подъёма host (проверено: host сам поднимается).

## Rollback

Убрать строку `Key([...] "p", lazy.spawn("pipboy-rofi open"))` из
`qtile/config.py` и перезапустить qtile. Хост/рофи-скрипт не затрагиваются.

## Не входит в scope

- TUI-плагин `/pipboy` (отдельный блокер, см.
  `[[07-Runbooks/pipboy-tui-smoke-test]]`).
- Автозапуск Pip-Boy при логине (не просилось; по умолчанию on-demand).