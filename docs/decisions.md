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

### ADR-008: S2 Theme hub (Aether-lite) — pywal + rofi
**Дата:** 2026-07-31
**Контекст:** Aether нравится по UX, но NVIDIA/WebKit баги. Нужен упрощённый theming hub «из приложения» без сторонней возни.
**Решение:**
- **Engine:** pywal (совместим с Qtile colors.py → `~/.cache/wal/colors.json`)
- **UI:** theme-hub (rofi) + оркестратор theme-apply
- wal-set → thin wrapper на theme-apply
- Хоткеи: `Mod+F5` = hub, `Mod+Shift+F5` = random
**Альтернативы:** wallust (адаптер colors.json); GTK/Wails app (дорого, NVIDIA-риск); полный aether (отклонён)
**Последствия:** S2 MVP/lite; wallust в пакетах но не hub; aether → deferred

---

### ADR-009: Эстетическая доктрина — cyberpunk ∩ solarpunk
**Дата:** 2026-07-31
**Контекст:** Устойчивое развитие dotfiles = не только утилитарность. Стиль и UX equally first-class. Нужен единый ориентир для всех агентов и будущих кастомизаций (лаунчеры, меню, бар, уведомления, theming).
**Решение:**
- **Стык cyberpunk ∩ solarpunk:** высокотехнологично, плавно, современно; при этом открыто, «живое», без мрачного гротеска и без корпоративного глянца.
- **Минимализм + hi-tech:** лёгкие UI (rofi/dunst/qtile), без тяжёлых GUI-конфигураторов; всплывающие меню, иконки, лаунчеры — уместны, если быстрые и осмысленные.
- **Скорость = часть эстетики:** задержка смены темы/обоев — дефект UX, не «норма».
- **Слои theming (связь с S2):** wallpaper layer ≠ bar layer; targets opt-in; не один random на всё.
- **Анимации:** уместные, короткие, функциональные (fade/flash палитры, notify), не декоративный шум.
- **Anti:** тяжёлый gloss, skeuomorphism, webkit-тяжёлые theme apps (aether-класс) как runtime-зависимость; DoomOne и прочие чужие fallback-палитры «на всякий случай».
**Альтернативы:** чистый cyberpunk / чистый solarpunk / «только минимализм без стиля» — отвергнуты как однобокие.
**Последствия:** user-profile, roadmap S2, theme-hub, qtile bar, rofi/dunst — выравниваются под доктрину. Все агенты читают этот ADR.

---

### ADR-010: S2 theming layers + engine + no-reload bar (уточнение ADR-008)
**Дата:** 2026-07-31
**Контекст:** MVP theme-hub работает, но reload_config роняет окна; pywal ощущается медленным; нужен контроль палитр per-layer; fallback DoomOne убрать.
**Решение:**
1. **Слои:** `wall` (обои+opt-in apps) | `bar` (отдельный palette-bar.json) | `apps` (targets.toml: wall|bar|preset|fixed).
2. **Смена обоев НЕ трогает бар** по умолчанию; бар — отдельное действие hub.
3. **Бар без reload_config:** live `refresh_bar_colors` + явная регистрация theme-targets в widgets (qtile-extras decorations).
4. **Engine:** уход с pywal как default runtime → **wallust** (быстрее extract) + адаптер/запись совместимого `~/.cache/wal/colors.json` ИЛИ прямой bar/wall json; pywal optional fallback only if wallust missing — NOT DoomOne palette.
5. **No DoomOne / no foreign preset fallback:** если палитры нет — последняя known-good из `~/.local/state/theme-hub/` или нейтральный минимальный dark из *нашей* base palette (cyber-solar), задокументированной в theme-hub, не DoomOne.
6. **Motion:** короткие feedback-анимации при apply (dunst + optional picom/rofi), без тяжёлого compositor show.
**Альтернативы:** оставить pywal+reload — отвергнуто (медленно + ломает сессию).
**Последствия:** план реализации частями 1–4; ADR-008 дополняется, не отменяется (rofi hub + scripts остаются).

---

### ADR-011: 22K Wallpaper Support — ImageMagick downscale + lossless PNG cache
**Дата:** 2026-08-02 (обновлено 2026-08-14: зафиксирована фактическая реализация)
**Контекст:** wallust имеет хардкодный лимит декода 512 MiB; 22K-изображения превышают его → OOM. Нужно прозрачное решение без ручной предобработки и без ущерба UX.
**Решение (фактическая реализация):**
- **Guard:** проверка размерностей перед wallust — `identify -format "%wx%h"`, downscale при >8192px по большей стороне или >100 MP.
- **Downscale:** ImageMagick `magick <img> -resize "3840x2160>" <png>` — подготовка 4K для wallust.
- **Lossless PNG cache:** даунскейл сохраняется как lossless PNG в `~/.cache/theme-hub/prepared/<hash>.png`.
- **Metadata key:** `stat -c '%n%s%Y' <img> | md5sum` (путь+размер+mtime, 12 hex) — дешёвый key без чтения пикселей.
- **Palette cache:** `~/.cache/theme-hub/palettes/<hash>.json` — на повторных изображениях палитра берётся из кэша, wallust не запускается.
- **Cache-hit restore consumers:** `restore_palette_cache` восстанавливает `~/.cache/wal/colors.json` + `colors-alacritty.toml` из кэша.
- **flock serialization:** `apply.lock` через `flock -n` / `flock -w 3` — параллельные apply не гоняют wallust одновременно; `--last` входит в общий lock-контур (`acquire_lock` в `main()` до ветвления, `trap release_lock EXIT`, 1a2230d).
**Trade-off (честно):**
- ImageMagick `-resize` — не streaming: высокий пик памяти на **первом** prepare большого изображения.
- Повторные apply — мгновенные cache hits (PNG prepared + palette cache + restore consumers).
**Почему не ffmpeg zimg:** фильтр `zimg` отсутствует в Manjaro ffmpeg (не скомпилирован `--enable-libzimg`, BUG-001); decode-limit wallust 512 MiB при этом остаётся. zimg/ffmpeg-путь отвергнут.
**Последствия:**
- 22K-изображения прозрачны для пользователя (авто-downscale до 4K).
- Первый прогон на 22K — заметный downscale (magick), повторно — мгновенно из кэша.
- Состояние всегда консистентно: оба пути (`--last` и основной) вызывают `update_state` → `wall.json` синхронен.
- Строгий fallback: при отсутствии palette cache для prev-wall `--last` завершается ошибкой — подстановка чужой/сохранённой палитры из state убрана (1a2230d).
**Альтернативы отвергнуты:**
- Смена бэкенда — все бэкенды упираются в тот же 512 MiB лимит.
- `ffmpeg zimg` — фильтр недоступен в Manjaro ffmpeg (BUG-001).
- Ручная предобработка пользователем — плохой UX, prone to user error.
**Статус:** Part 1 S2 (wall layer) COMPLETE; Part 2 S2 (bar layer, live refresh без reload_config) — in progress.

---

### ADR-012: Markdown Workbench
**Дата:** 2026-08-17

**Проблема/контекст:** Markdown — основной формат заметок, спецификаций и runbook-файлов, но сейчас нет единого terminal-native рабочего процесса. Neovim (LazyVim) должен быть быстрым редактором с live-rendering, Ranger — точкой навигации и предпросмотра, а Glow — независимым полноэкранным fallback/viewer. Компоненты должны жить в отдельных Stow-пакетах, не дублировать источник правды и не превращать просмотр Markdown в тяжёлый GUI.

**Решение:**
- Описать и реализовать Markdown Workbench как связку `nvim/.config/nvim/` + `ranger/.config/ranger/`, без нового отдельного пакета.
- Подключить `MeanderingProgrammer/render-markdown.nvim` через LazyVim spec с явным `opts`, используя публичные команды/API плагина для toggle/enable/disable; `lazy-lock.json` намеренно обновлён до commit `4663eb3ecd538bd5062628fb6d95bbe6bdca78f6` для воспроизводимости.
- Сохранить исходный Markdown единственным source-of-truth; render-markdown.nvim отвечает только за представление буфера, а Glow — за внешний просмотр.
- Расширить Ranger preview через существующий `scope.sh` с проверяемым наличием Glow и безопасным текстовым fallback; запуск Glow из Ranger — отдельное действие, не подмена редактора.
- Зафиксировать mappings, fallback, зависимости, границы и smoke tests в `docs/specs/markdown-workbench.md`; операционные процедуры — в `docs/runbooks/markdown-workbench.md`.

**Альтернативы:**
- Только Glow — отвергнуто: нет редактирования и live-rendering.
- Только render-markdown.nvim — отвергнуто: просмотр из файлового менеджера и аварийный путь зависят от Neovim.
- GUI Markdown-приложение или browser/WebKit — отвергнуто: лишние зависимости, задержка и нарушение terminal-native UX.
- Дублировать Markdown в HTML/PDF — отвергнуто: два источника правды и stale-артефакты.
- Новый Stow-пакет `markdown/` — отвергнуто: настройка принадлежит существующим владельцам `nvim` и `ranger`.

**Последствия:**
- Быстрый единый путь: навигация в Ranger → preview/Glow → редактирование в Neovim.
- Добавляются внешние optional/runtime зависимости Glow и Treesitter Markdown; отсутствие Glow не ломает Ranger или Neovim.
- API плагина и формат его lock-записи требуют проверки при обновлении; lock-файл может изменяться, если обновление намеренно фиксирует нужный commit для воспроизводимости. Smoke tests выполняются verifier и учитываются только при наличии факта их выполнения.
- Conceal/rendering остаются presentation-layer: файл на диске не изменяется.

**Границы:**
- Первый этап — контракт и документация; реализация использует существующие владельцы `nvim` и `ranger`, а `lazy-lock.json` намеренно изменён для фиксации commit render-markdown.nvim. README и roadmap не меняются.
- Решение намеренно ограничено Markdown пользовательским scope; Quarto не является требованием и не входит в контракт.
- Не входят Markdown LSP, note-taking workflow, wiki/backlinks, экспорт, синхронизация, автокоммиты и управление пакетами.
- Не входят правки `/etc`, systemd, глобальных переменных окружения и секретов.
