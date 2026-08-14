---
type: Roadmap
title: Roadmap dotfiles — карта системы
description: Потоки способностей, зависимости, Now/Next/Later. Не inventory пакетов.
timestamp: 2026-07-31
status: active
---

# Roadmap dotfiles

> Карта **системы**, не список пакетов. Карточка = способность + DoD + зависимости.
> OpenCode-Vault (`~/Projects/OpenCode-Vault/`) — внешний оркестратор проектов; здесь не разрабатывается.

## Карта

```
Stow + пакеты (S0)
    ├─→ Desktop: Qtile · rofi · dunst · picom (S1)
    ├─→ Terminal: zsh · tmux · nvim · Alacritty (S4)
    └─→ Theming hub (S2) ──блокирует──→ эстетика S1/S3/S4
              ↓
         Daily tools (S3): clipboard · media · images · volume
              ↓
         Machine ops (S5): hygiene · bootstrap · secrets
              ↓
         Parked (S6) → docs/deferred.md
```

## Now / Next / Later

| Слот | Поток | Что сделать |
|------|--------|-------------|
| **Now** | S2 Part 2 | Bar layer: live refresh без reload_config + palette menu (ADR-010/011) |
| **Next** | S2 polish | Шаблоны GTK/dunst/rofi; motion feedback |
| **Later** | S3→S1→S4→S5 | Daily tools под stow+тему; polish desktop; cheats; bootstrap |
| **Parked** | S6 | Taskwarrior, calcurse, aether, Docker… → deferred.md |

## Потоки

### S0 · Фундамент
**Зачем:** всё остальное живёт на stow без дрейфа и без забитого `/`.
**DoD:** stow-пакеты консистентны; на `/` >10G свободно; `disk-hygiene` доступен как `~/.local/bin/disk-hygiene`.
**Статус:** ~95%
- [x] sysaudit, ADR, deferred, pipelines
- [x] дрейф systemd / wal / gtk (css + gtk-4 settings.ini)
- [x] Qtile modular + `~/.config/qtile` symlink
- [x] picom → `~/.config/picom/picom.conf`
- [x] nvim under stow (file-level)
- [x] usb-manager, agent infra (stow-ops, verifier, /fix /test)
- [x] скрипт `scripts/.local/bin/disk-hygiene` в репо
- [x] **`stow scripts`** — `disk-hygiene` в `~/.local/bin/`, symlink в stow-пакет
- [ ] **Диск:** прогон disk-hygiene + `paccache`/`journalctl` (root) → >10G free

### S1 · Desktop shell
**Зачем:** Qtile + rofi + dunst + picom ощущаются одним UI.
**Зависит от:** S0; полноценная эстетика — от S2.
**DoD:** единые хоткеи/поведение; уведомления и лаунчер не «чужие» по теме.
**Статус:** база есть (Qtile/picom ok), polish после S2
- Qtile ✅ · picom ✅ · rofi/dunst — донастройка темы после S2

### S2 · Theming hub  ← Now (Part 2)
**Зачем:** один генератор цвета → Alacritty, rofi, dunst, GTK, Qtile, terminal.
**Зависит от:** S0.
**Блокирует:** визуальный polish S1/S3/S4.
**DoD:** смена обоев/палитры перекрашивает стек без ручной правки N утилит.
**Доктрина:** ADR-009 (cyberpunk ∩ solarpunk) + ADR-010 (layers + engine + no-reload bar) + ADR-011 (22K downscale + caches)
**Статус:** Part 1 (wall layer) DONE; Part 2 (bar layer) IN PROGRESS

#### Part 1 · wall layer — DONE (2026-08-02, подтверждено 2026-08-14)
- [x] Выбран основной генератор: **wallust** (pywal fallback убран, wallust обязателен — ADR-010/011)
- [x] Оркестратор `theme-apply` + rofi-меню `theme-hub`
- [x] Хоткеи: `Mod+F5` hub, `Mod+Shift+F5` random
- [x] `wal-set` → thin wrapper на `theme-apply`
- [x] **22K support:** guard >8192px/>100MP, ImageMagick `magick -resize 3840x2160>` + lossless PNG cache в `~/.cache/theme-hub/prepared/` (ADR-011)
- [x] **Palette cache:** stat+md5 metadata key, кэш в `~/.cache/theme-hub/palettes/`, cache-hit восстанавливает colors.json + alacritty без wallust
- [x] **Lock serialization:** `flock` на `apply.lock` — параллельные apply сериализованы; `--last` в общем lock-контуре (1a2230d)
- [x] **`--last` history:** повтор последних обоев + state-sync (`update_state` в обоих путях); при отсутствии palette cache — ошибка, без fallback на чужую палитру (1a2230d)
- [x] **Trade-off:** первый 22K prepare — высокий пик памяти ImageMagick; повторные apply — мгновенные cache hits
- [x] **Code efficiency:** theme-apply ~320 строк (169 → 320 после palette cache + lock), helpers извлечены (TD-001)

#### Part 2 · bar layer — IN PROGRESS (блокеров нет, timeline: эта неделя)
- [ ] **Bar live refresh:** `refresh_bar_colors` без `reload_config` (ADR-010)
- [ ] **Palette menu:** отдельный слой `bar` в theme-hub
- [ ] **Слои:** wall | bar | apps — раздельные палитры, смена обоев НЕ трогает бар (ADR-010)
- [ ] **Motion feedback:** короткие анимации при apply (dunst + picom/rofi)
- [ ] Больше шаблонов (GTK, dunst, rofi — polish)
- [ ] aether — НЕ здесь (NVIDIA) → deferred.md

### S3 · Daily utilities
**Зачем:** повседневные GUI/утилиты в stow и согласованы с темой — не «голые пакеты из pacman».
**Зависит от:** S0; тема — от S2 (можно сначала просто захват конфигов).
**DoD:** clipboard, media, image viewer, volume — конфиги в репо, stow clean.
**Было ошибочно в Ready как «пакет copyq/viewnior/volumeicon»** — это не цели, а *элементы* потока:
| Элемент | Смысл |
|---------|--------|
| copyq | история буфера, хоткей, поведение |
| mpv | минимальный воспроизводимый UX |
| viewnior (или выбранный viewer) | быстрый просмотр из ranger/rofi |
| volumeicon / pactl UX | индикация/контроль громкости, если ещё дыра после Qtile |
| nitrogen | только если нужен отдельно от wal-set обоев |

### S4 · Terminal craft
**Зачем:** zsh/tmux/nvim/Alacritty — быстрый ежедневный контур + подсказки.
**Зависит от:** S0; цвета — от S2.
**DoD:** стабильный dev-loop; cheatsheets для nvim/tmux/zsh/git по запросу.
**Статус:** база есть; cheats — later

### S5 · Machine ops
**Зачем:** гигиена диска, bootstrap новой машины, секреты вне git.
**Зависит от:** S0.
**DoD:** `disk-hygiene` в PATH; документированный bootstrap; схема secrets out-of-repo.
**Статус:** disk-hygiene в репо; bootstrap/secrets — later

### S6 · Parked
Всё «на потом» и артефакты — только в `docs/deferred.md` (Taskwarrior, calcurse, Thunar, Hyprland, kitty, aether, Docker, плагины…).
Сюда не тащить в Now/Next.

## Зависимости (кратко)

```
S0 ──→ S2 ──→ S1 polish
 │      └──→ S3 themed
 │      └──→ S4 colors
 └──→ S5
S6 = вне критического пути
```

## Открытые решения (разблокируют Next)

1. ~~**S2:** что реально основной генератор сейчас — pywal / wallust / tinty?~~ → **wallust** (ADR-010/011) ✅
2. После S0 сразу **S2 polish** (шаблоны GTK/dunst/rofi) или временно S3 capture-only?

## Milestone Done (не список коммитов)

- [x] S0 foundation (кроме диска: >10G free на `/`)
- [x] Qtile modular + stow adopt
- [x] Agent infra + drift capture
- [x] OpenCode-Vault = external (не работа dotfiles)
