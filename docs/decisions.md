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

### ADR-004: Прокси — Happ proxy primary (System Proxy mode), Tor 9050 fallback, режимы через proxyctl
**Дата:** 2026-07-01 (обновлено 2026-07-14: TUN → System Proxy mode)

**Контекст:** Два источника прокси-соединения: Happ (режим System Proxy, SOCKS5h 127.0.0.1:10808) и Tor (SOCKS5 127.0.0.1:9050). Happ больше не использует TUN — работает через системный прокси-порт. Нужна автоматизация переключения без sudo/рестартов, с возможностью фиксировать режим вручную.

**Решение:**
- **ALL_PROXY** — единый env-эндпоинт (socks5h://127.0.0.1:10808 для Happ, socks5://127.0.0.1:9050 для Tor, пусто для off). Устанавливается через `~/.config/environment.d/proxy.conf` (systemd user environment.d) и `systemctl --user set-environment`.
- **proxyctl** — CLI для управления режимами: `happ`, `tor`, `off`, `status`, `mode <auto|happ|tor|off>`. Пишет текущий режим в `~/.config/proxyctl/mode`. `happ` устанавливает ALL_PROXY на 10808, `tor` на 9050.
- **proxy-healthcheck** — systemd-таймер (15s после boot, каждые 30s). Читает mode: если `auto` — проверяет порт 10808 (через `ss -tlnp | grep 10808`); активен → `proxyctl happ`, иначе → `proxyctl tor`. Если mode != auto — exit 0 (не оверрайдит ручной выбор).
- **proxy-on-login.service** — устанавливает `mode auto` при логине.

**Альтернативы:**
- Таймер без mode (всегда auto) — отвергнуто: оверрайдит `off` при следующем тике таймера.
- Ручное управление без таймера — отвергнуто: нет автопереключения при старте/стопе Happ proxy.
- Все режимы через systemd user units без CLI — отвергнуто: неудобно менять режим вручную.
- TUN-режим Happ — отвергнуто: TUN нестабилен, переход на System Proxy mode.

**Последствия:**
- `off` сохраняется, пока пользователь явно не сменит mode (таймер не оверрайдит).
- Минимальный оверхед: `ss -tlnp | grep` каждые 30s + oneshot systemd.
- Зависимость от `~/.config/proxyctl/mode` — loss of state при удалении файла (корректно: default auto).
- `systemctl --user` не обязателен (graceful fallback).
- Больше никаких TUN/TAP-интерфейсов в проверках — только проверка порта.

---

### ADR-005: USB Manager — GUI-утилита управления накопителями
**Дата:** 2026-07-13
**Контекст:** Нужен удобный интерфейс для USB-накопителей: автодетект, просмотр содержимого, действия (mount/unmount/eject). Интеграция с треем, уведомлениями, горячими клавишами.

**Решение:**
- **Стек:** Python 3 + GTK3 + udisks2 (DBus) + pyudev
- **Архитектура:**
  1. **usb-manager** — основной GUI (GTK3 Application)
  2. **usb-daemon** — systemd user service, слушает udev события через pyudev
  3. **usb-cli** — CLI wrapper для вызова из Qtile/rofi
  4. **udev rule** — триггер для systemd service при подключении USB
- **Функциональность:**
  - Tray icon (ayatana-appindicator) с меню
  - Автопоказ окна при подключении USB
  - Список файлов накопителя (tree view)
  - Действия: mount, unmount, eject, open in ranger
  - Уведомления через dunst (dbus)
  - Горячая клавиша: `Mod+u` (настраивается)
- **Стиль:**
  - Тёмная тема (CSS, совместимо с wal)
  - Моноширинный шрифт (JetBrains Mono)
  - Минималистичный интерфейс (без лишних кнопок)
- **Интеграция:**
  - Qtile: keybinding `Mod+u` → `usb-cli toggle`
  - Dunst: уведомления о подключении/действии
  - Ranger: `usb-cli open` открывает накопитель в ranger

**Альтернативы:**
- **PyQt5/6** — отвергнуто: тяжелее, менее нативно для GTK-окружения
- **Tkinter** — отвергнуто: устаревший вид, плохая стилизация
- **Shell + dmenu/rofi** — отвергнуто: нет tree view, неудобен для просмотра файлов
- **udiskie** — отвергнуто: недостаточно кастомизации, чужой стиль

**Последствия:**
- Новый пакет `usb-manager/` в dotfiles
- Зависимости: `python-gobject`, `udisks2`, `python-pyudev`, `libayatana-appindicator`
- systemd user service: `usb-daemon.service`
- Интеграция с Qtile (hotkey), dunst (notifications)
- ~500-700 строк Python кода

**Статус реализации (2026-07-13):**
- ✅ Пакет `usb-manager/` создан (7 файлов)
- ✅ Компоненты: GUI (GTK3), daemon (pyudev), CLI (argparse)
- ✅ Интеграция: systemd service, udev rule, tray icon
- ✅ Документация: README.md с инструкциями
- ✅ ADR-006: автоматизация тестирования (verifier, /test, /fix)
- ✅ Базовая функциональность: список USB, дерево файлов, Mount/Unmount/Eject
- ⚠️ Известные проблемы:
  - Open in Ranger — не работает (отложено)
  - DeprecationWarning pyudev — не критично
  - Dunst уведомления — требуют запуска dunst
- ⏳ Требуется: udev rule в /etc/udev/rules.d/ (ручная установка)

---

### ADR-006: Автоматизация тестирования и верификации — проблема "ручного цикла"
**Дата:** 2026-07-13
**Контекст:** При разработке USB Manager возникла проблема: после каждого изменения кода (util-dev) нужно вручную запускать проверки (`python3 -m py_compile`, `systemctl restart`, `journalctl`, тестирование с флешкой). Planner не может выполнять bash-команды (ограничения permission rules), util-dev тоже ограничен. Это создаёт "ручной цикл" — пользователь вынужден копипастить команды.

**Проблема:**
1. **Permission rules** блокируют: `python3 -m py_compile`, `systemctl restart`, `journalctl`, `chmod`
2. **Нет агента-тестировщика** — verifier существует, но его роль ограничена "stow dry-run"
3. **Разорванный пайплайн** — builder создаёт код, но не может его проверить
4. **Пользователь = CI** — Макс вынужден выполнять роль CI/CD системы

**Решение:**
Расширить роль **verifier** агента и создать пайплайн `/test`:

1. **verifier** получает расширенные права:
   - `python3 -m py_compile` — проверка синтаксиса
   - `systemctl --user status/restart` — управление user services
   - `journalctl --user -u` — чтение логов
   - `ls -la`, `cat` — проверка файлов
   - `stow -n` — dry-run проверка

2. **Пайплайн `/test`:**
   ```
   /test <пакет> → verifier
   ```
   Verifier автоматически:
   - Проверяет синтаксис Python-скриптов
   - Проверяет stow dry-run
   - Проверяет статус systemd services
   - Читает логи на наличие ошибок
   - Возвращает отчёт: PASS/FAIL + детали

3. **Пайплайн `/fix`:**
   ```
   /fix <пакет> → util-dev/bash-dev → verifier
   ```
   Автоматический цикл: исправить → проверить → если FAIL, исправить снова (до 3 итераций)

4. **Permission rules** — добавить в opencode.json:
   ```json
   {"permission": "bash", "pattern": "python3 -m py_compile*", "action": "allow"},
   {"permission": "bash", "pattern": "systemctl --user status*", "action": "allow"},
   {"permission": "bash", "pattern": "systemctl --user restart*", "action": "allow"},
   {"permission": "bash", "pattern": "journalctl --user*", "action": "allow"},
   {"permission": "bash", "pattern": "chmod +x*", "action": "allow"}
   ```

**Альтернативы:**
- **Создать нового агента "executor"** — отвергнуто: дублирует verifier, лучше расширить существующего
- **Полностью открыть bash** — отвергнуто: нарушение безопасности, нужен принцип минимальных привилегий
- **Пользователь запускает всё вручную** — отвергнуто: это и есть проблема, которую решаем
- **CI/CD через GitHub Actions** — отвергнуто: dotfiles — локальный проект, CI избыточен

**Последствия:**
- Расширение роли verifier (нужно обновить `.opencode/subagent/verifier.md`)
- Добавление пайплайнов `/test` и `/fix` (нужно создать `.opencode/command/test.md` и `fix.md`)
- Изменение permission rules в `opencode.json`
- Ускорение разработки: автоматическая проверка после каждого изменения
- Снижение нагрузки на пользователя: не нужно копипастить команды

**Приоритет реализации:**
1. Permission rules (быстро, сразу разблокирует проверки)
2. Расширение verifier (средне, нужно обновить инструкции)
3. Пайплайн `/test` (быстро, обёртка над verifier)
4. Пайплайн `/fix` (сложнее, требует цикла build→verify→fix)

**Статус реализации (2026-07-13):**
- ✅ Verifier agent добавлен в opencode.json (строки 220-251)
- ✅ Permission rules расширены (python3 -m py_compile, systemctl --user restart, journalctl)
- ✅ util-dev права расширены (py_compile, systemctl status, journalctl)
- ✅ Пайплайн `/test` создан (.opencode/command/test.md, 78 строк)
- ✅ Пайплайн `/fix` создан (.opencode/command/fix.md, 59 строк)
- ⏳ Требуется: перезапуск OpenCode для применения изменений
-  Тестирование: `/test usb-manager`, `/fix usb-manager`

---

### ADR-007: Роутинг агентов — дифференциация моделей по ярусам ролей
**Дата:** 2026-07-20
**Контекст:** Все 9 агентов работают на одной модели `deepseek-v4-flash-free` (однородный роутинг). У пользователя активны 2 подписки — `opencode-go` и `opencode-zen` — и опробованы модели: Qwen, Haiku, Kimi, GLM, Grok, DeepSeek, hy3. Разные агенты делают разную работу по цене/качеству: planner нуждается в сильном рассуждении, dev-агенты — в генерации кода, audit/verify — в быстрых дешёвых ответах. Однородный роутинг не использует доступные подписки и недогружает planner.

**Решение:** Разбить агентов на 3 яруса и назначить модели из опробованного набора:

| Ярус | Агенты | Модель |
|------|--------|--------|
| **Reasoning** | `planner` | **Haiku** (хайку) |
| **Coding** | `builder`, `qtile-dev`, `bash-dev`, `util-dev`, `stow-ops` | **Qwen** (квен) |
| **Light** | `sysop`, `reviewer`, `verifier` | **DeepSeek** (дипсик) |

**Исправление (2026-07-20):** по указанию пользователя Reasoning↔Light обменяны местами: `planner` → Haiku, `sysop`/`reviewer`/`verifier` → DeepSeek (исходно в этом ADR было наоборот). |

Резерв: **Kimi** (длинный контекст — альт. planner при больших ADR), **GLM** (код — альт. coding), **Grok** (general), **hy3** (текущая free-модель, fallback при недоступности подписочной модели). Точные `model` ID прописываются в `opencode.json` (`agent.<name>.model`) и резолвятся из подписок `opencode-go` / `opencode-zen`.

**Альтернативы:**
- Оставить однородным (`deepseek-v4-flash-free`) — отвергнуто: не использует доступные подписки, planner недополучает рассуждение.
- Всех на одну сильную модель (DeepSeek) — отвергнуто: audit/verify становятся дорогими и медленными.
- Уникальная модель каждому агенту — отвергнуто: избыточно, 3 яруса покрывают различия.

**Последствия:**
- Правка `opencode.json`: `agent.<name>.model` для 9 агентов (см. задачу builder).
- Обновление таблицы роутинга в `AGENTS.md`.
- Ожидаема разница в латентности/качестве между ярусами.
- `hy3` остаётся fallback.

---

### ADR-008: Chromium запускается через единый HAPP-aware wrapper
**Дата:** 2026-08-29
**Контекст:** HAPP на `127.0.0.1:10808`/`10809` подтверждён через `curl`, а
Chromium с явным proxy flag и чистым профилем работает. Системный desktop entry
запускает Chromium напрямую; уже существующий singleton-процесс не принимает
proxy flag второго запуска.
**Решение:** Обычный Chromium запускается через версионируемый stow-wrapper,
который учитывает режим `proxyctl`; пользовательский `chromium.desktop` и
обычные launch-paths направляются в wrapper. Добавить Qtile hotkey `Super+G`
для обычного Chromium; существующий `Super+Shift+G` для Genspark/Tor сохранить.
Специальные Tor web-apps и TUN не изменяются.
**Альтернативы:** env-переменные отвергнуты из-за поведения Chromium; ручной
flag отвергнут из-за отсутствия автоматизации; TUN отвергнут по ADR-004.
**Последствия:** Единый proxy entrypoint для Chromium; при смене proxy mode
нужен полный выход Chromium. Спека реализации должна быть зафиксирована рядом
с ADR и содержать DoD для Stow, desktop entry, Qtile и Tor-приложений.
