# Архитектурные решения (ADR) — dotfiles

> Реестр ADR. Новые решения добавляются в конец.

---

### ADR-001: Инициализация OpenCode в dotfiles
**Дата:** 2026-06-30
**Контекст:** Dotfiles — 23 пакета конфигов, управляемых через GNU Stow.
**Решение:**
- 3 primary агента: sysop, planner, builder
- 4 subagent: reviewer, qtile-dev, bash-dev, util-dev
- 8 команд-пайплайнов
**Альтернативы:** Один универсальный агент — отвергнуто.
**Последствия:** Dotfiles — управляемый проект с пайплайнами.

---

### ADR-002: Настройка xdg-desktop-portal для Flameshot
**Дата:** 2026-06-30
**Контекст:** После ребута Flameshot v14 перестал делать скриншоты на X11/Qtile. Ошибка: `org.freedesktop.portal.Desktop` не найден.
**Решение:**
1. Полный override unit для xdg-desktop-portal: убран Requisite= и After=graphical-session.target (drop-in не работает на systemd 260)
2. environment.d/90-desktop.conf с XDG_CURRENT_DESKTOP=qtile
3. export + import-environment в autostart-x11
4. Перемещён dunst перед flameshot
**Альтернативы:**
- Запускать portal напрямую (/usr/lib/xdg-desktop-portal &) — не systemd-way
- Заменить flameshot на maim/scrot — потеря GUI-редактора
- Wrapper для graphical-session.target — сложнее override
**Последствия:** Portal работает без graphical-session.target (Requisite= удалён). Вместо drop-in — полный override unit (systemd 260 не сбрасывает Requisite= через пустое значение). Порядок сервисов: env → portal → dunst → flameshot.

**Резолюция (2026-06-30):** Portal-fixes оказались ложным следом. 
Реальная причина: регрессия Flameshot v14 + Qt 6.11 + NVIDIA на X11 — 
`QScreen::grabWindow()` зависает в XCB/NVIDIA. Решение: даунгрейд 
до `flameshot-imgur` (v13.3.0) — работает стабильно, тот же бинарник 
`/usr/bin/flameshot`, все фичи сохранены.

---

### ADR-003: tmux — гибридное управление плагинами (submodule + full clone)
**Дата:** 2026-07-01
**Контекст:** Tmux — основной терминальный мультиплексор. Используются плагины: 
tpm (менеджер), tmux-resurrect, tmux-continuum, tmux-yank, tmux-open, 
tmux-sensible, vim-tmux-navigator. Критично сохранение/восстановление сессий 
через tmux-resurrect + continuum.

**Решение:**
- **tpm** — git submodule (pinned к коммиту e261deb). Как менеджер плагинов, 
  он обновляется отдельно, его код не меняется. Submodule позволяет 
  зафиксировать версию и не захламлять историю dotfiles.
- **Остальные плагины** — full clone в `tmux/plugins/`. Причина: 
  tmux-resurrect и continuum должны быть доступны сразу после установки 
  dotfiles без дополнительного шага `prefix + I` (установка через tpm). 
  Это гарантирует корректное восстановление сессий даже до первого запуска 
  tpm. Full clone также упрощает bootstrap новых машин.

**Альтернативы:**
- Все плагины через tpm (submodule только tpm) — отвергнуто: требует 
  ручного `prefix + I` после каждого stow, сессии не восстанавливаются 
  до первого запуска tpm.
- Все плагины как submodule — отвергнуто: избыточный overhead, 7+ submodule 
  ссылок, сложности с обновлением.
- Все плагины как full clone — допустимо, но tpm pinned как submodule для 
  явного контроля версии менеджера.

**Последствия:**
- После `stow tmux` всё работает сразу, без дополнительных действий.
- tpm обновляется отдельно: `git submodule update --remote tmux/plugins/tpm`.
- Плагины занимают место в репо (~несколько МБ), но это компромисс ради 
  надёжности восстановления сессий.
- При добавлении нового плагина: full clone в tmux/plugins/ + register в .tmux.conf.

---

### ADR-004: Прокси — Happ TUN primary, Tor 9050 fallback, режимы через proxyctl
**Дата:** 2026-07-01
**Контекст:** Два источника прокси-соединения: Happ (TUN-интерфейс, transparent proxy) и Tor (SOCKS5 127.0.0.1:9050). Нужна автоматизация переключения без sudo/рестартов, с возможностью фиксировать режим вручную.

**Решение:**
- **ALL_PROXY** — единый env-эндпоинт (socks5://127.0.0.1:9050 для Tor, пусто для Happ/off). Устанавливается через `~/.config/environment.d/proxy.conf` (systemd user environment.d) и `systemctl --user set-environment`.
- **proxyctl** — CLI для управления режимами: `happ`, `tor`, `off`, `status`, `mode <auto|happ|tor|off>`. Пишет текущий режим в `~/.config/proxyctl/mode`.
- **proxy-healthcheck** — systemd-таймер (15s после boot, каждые 30s). Читает mode: если `auto` — детектит TUN/TAP/HAPP (через `ip link`); найден → `proxyctl happ`, иначе → `proxyctl tor`. Если mode != auto — exit 0 (не оверрайдит ручной выбор).
- **proxy-on-login.service** — устанавливает `mode auto` при логине.

**Альтернативы:**
- Таймер без mode (всегда auto) — отвергнуто: оверрайдит `off` при следующем тике таймера.
- Ручное управление без таймера — отвергнуто: нет автопереключения при старте/стопе Happ TUN.
- Все режимы через systemd user units без CLI — отвергнуто: неудобно менять режим вручную.

**Последствия:**
- `off` сохраняется, пока пользователь явно не сменит mode (таймер не оверрайдит).
- Минимальный оверхед: `ip link | grep` каждые 30s + oneshot systemd.
- Зависимость от `~/.config/proxyctl/mode` — loss of state при удалении файла (корректно: default auto).
- `systemctl --user` не обязателен (graceful fallback).
