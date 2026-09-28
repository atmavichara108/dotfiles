---
type: Execution Spec
title: Pip-Boy хоткей (dotfiles / qtile)
project: dotfiles
status: accepted
timestamp: 2026-09-18
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

## Конфликты клавиш

При анализе `qtile/.config/qtile/keys.py` обнаружены конфликты:

| Клавиша | Занята | Назначение |
|---|---|---|
| `mod4 + p` | **KeyChord** | dm-scripts hub (dm-hub, dm-sounds, dm-setbg, …) — `keys.py:124` |
| `mod4 + b` | **Key** | `lazy.hide_show_bar(position='all')` — bar toggle — `keys.py:40` |

Обе клавиши (`p` и `b` без модификаторов) заняты, поэтому прямое назначение
`mod4 + p` или `mod4 + b` невозможно без поломки существующего функционала.

## Решение

Назначен безопасный хоткей **`Super + Shift + P`** — свободен, не конфликтует
ни с одним существующим биндингом:

```python
Key([mod, "shift"], "p", lazy.spawn("pipboy-rofi open"), desc="Pip-Boy"),
```

- Добавлен в `qtile/.config/qtile/keys.py` в секции app launchers (после
  Genspark, перед layout shuffle keys).
- `pipboy-rofi open` идемпотентен: если host поднят — просто откроет браузер,
  если нет — поднимет и откроет. Никакой новой логики писать не надо.
- Existing KeyChord `mod4 + p` **не тронут**.

## DoD

- [x] Хоткей `Super+Shift+P` добавлен в `qtile/.config/qtile/keys.py`.
- [ ] `python -m py_compile` — синтаксис без ошибок (проверено локально, cache в /tmp).
- [ ] `qtile cmd-obj -o cmd -f restart` (или `qtile shell` → `restart`) — конфиг без ошибок.
- [ ] Нажатие `Super+Shift+P` открывает Pip-Boy в браузере; повторное — не плодит вкладки.
- [ ] `pipboy-rofi open` вызывается без ручного подъёма host (проверено: host сам поднимается).
- [ ] Существующий KeyChord `Super+P` (dm-scripts) продолжает работать.

## Rollback

Убрать строку `Key([mod, "shift"], "p", lazy.spawn("pipboy-rofi open"), desc="Pip-Boy")`
из `qtile/.config/qtile/keys.py` и перезапустить qtile. Хост/рофи-скрипт не
затрагиваются.

## Не входит в scope

- TUI-плагин `/pipboy` (отдельный блокер, см.
  `[[07-Runbooks/pipboy-tui-smoke-test]]`).
- Автозапуск Pip-Boy при логине (не просилось; по умолчанию on-demand).