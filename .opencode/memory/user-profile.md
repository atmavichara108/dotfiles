---
type: User Profile
title: Профиль пользователя — Макс
description: Кто такой Макс, как работает, что ценит, предпочтения UX.
timestamp: 2026-07-31
---

# Профиль пользователя — Макс

> Этот файл читают все агенты dotfiles перед работой. Он определяет **для кого** ты строишь.

## Кто такой

- **Вайбкодер** — строит системы, где ИИ делает работу, а он проектирует пайплайны
- **Системный инженер** — мыслит в терминах петель, конвейеров, протоколов
- **Минималист** — ничего лишнего, каждый элемент осмыслен
- **OpenCode-пользователь** — основной инструмент разработки

## Как работает

- **Русский язык** — думает и работает на русском
- **Терминал** — zsh + tmux + neovim — основная среда
- **WM** — Qtile (Python-based, кастомизируемый)
- **Терминал-эмулятор** — Alacritty (быстрый, минималистичный)
- **Лаунчер** — Rofi
- **Уведомления** — Dunst

## Что ценит

### Визуально
- **Доктрина:** cyberpunk ∩ solarpunk (ADR-009) — hi-tech + открытость, без глянца и гротеска
- **Тёмная тема** — база; светлые акценты «solarpunk» (тепло/зелень/янтарь) точечно
- **Минимализм** — чистый UI; стиль = first-class наравне с утилитарностью
- **Скорость отклика** — часть красоты (theme apply, rofi, bar)
- **Лёгкие поверхности:** rofi/dunst/qtile menus, не тяжёлые GUI
- **Консистентность** — слои theming (wall/bar/apps), не один random на всё
- **Motion** — короткие уместные анимации
- **Anti:** DoomOne fallback, webkit theme apps как dependency, excess gloss

### Функционально
- **Эффективность кода** — lean hot path; см. TD-001
- **Скорость** — мгновенный отклик, никаких лагов
- **Автоматизация** — если можно заскриптовать, не делай руками
- **Модульность** — каждый пакет независим (GNU Stow)
- **Документированность** — чит-шиты, ADR, комментарии в нетривиальных местах

### В разработке
- **Строгий режим** — `set -euo pipefail`, type hints, lint
- **Безопасность** — никаких секретов в репо
- **Git** — атомарные коммиты, conventional commits

## Предпочтения по инструментам

| Инструмент | Предпочтение | Почему |
|-----------|-------------|--------|
| Shell | zsh + powerlevel10k | Быстрый, красивый промпт |
| WM | Qtile | Python, кастомизируемый, тайлинг |
| Editor | Neovim | Быстрый, плагины, terminal-native |
| Terminal | Alacritty | GPU-ускоренный, минималистичный |
| File manager | Ranger | Terminal-native, vim-ключи |
| Launcher | Rofi | Быстрый, кастомизируемый |
| Monitor | btop | Красивый, информативный |
| Git TUI | lazygit | Быстрый, наглядный |

## Anti-goals (чего НЕ хочет)

- **Тяжёлые IDE** — VS Code, JetBrains — слишком медленные
- **Графические конфигураторы** — только текст
- **Сложные setup-скрипты** — если не работает с первого раза, это баг
- **Хардкод путей** — всё через переменные
- **Секреты в репо** — никогда
- **Дублирование конфигов** — один источник правды

## Контекст системы

- **OS:** Manjaro (Arch-based)
- **DE:** Нет, чистый Qtile
- **Display:** X11 (не Wayland)
- **Home:** `/home/rudra/`
- **Dotfiles:** `/home/rudra/dotfiles/` (GNU Stow)

## Последние изменения (2026-07-01)

- **Браузер:** Chromium вместо Google Chrome
- **Добавлено в окружение:** nvm, bun, direnv
- **Git pull:** rebase = true
- **LSP в OpenCode:** включён
- **Tmux:** гибридная архитектура плагинов (ADR-003)
- **Токены/секреты:** вынесены из репо (артефакт удалён)

## S2 Theming hub — прогресс (2026-08-02)

### Part 1 · wall layer — COMPLETE
- **22K support:** guard >8192px / >100MP; ImageMagick `magick -resize 3840x2160>` + lossless PNG cache в `~/.cache/theme-hub/prepared/` (ADR-011). zimg/ffmpeg отвергнут — фильтр недоступен в Manjaro ffmpeg (BUG-001).
- **Palette cache:** stat+md5 metadata key (`stat -c '%n%s%Y'`), кэш `~/.cache/theme-hub/palettes/`, cache-hit восстанавливает colors.json + alacritty без wallust.
- **Lock serialization:** flock на `apply.lock` — параллельные apply не конфликтуют.
- **`--last` history:** повтор последних обоев с синхронизацией state (`prev-wall` → `last-wall` → `wall.json`).
- **State-sync fix:** оба пути (`--last` и основной) вызывают `update_state` → `wall.json` всегда консистентен (state-drift устранён).
- **Trade-off:** первый 22K prepare — высокий пик памяти ImageMagick; повторные apply — мгновенные cache hits.
- **Ключевые решения:** ImageMagick для downscale (не ffmpeg zimg — недоступен, BUG-001); pywal fallback убран, wallust обязателен.
- **Code efficiency:** theme-apply ~320 строк (рост после palette cache + lock), helpers извлечены, DRY (см. TD-001).

### Next · Part 2 · bar layer — IN PROGRESS
- Live refresh палитры бара без `qtile reload_config` (`refresh_bar_colors` + регистрация theme-targets).
- Palette menu в theme-hub (отдельный слой `bar`).
- Blockers: нет. Timeline: на этой неделе.
