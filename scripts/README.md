# scripts

Скрипты в `~/.local/bin/` через GNU Stow (`stow scripts`).

## Темы (S2 theme-hub, ADR-010)

### Слои

- **wall** — обои + палитра + feh + dunst + lockscreen. Не трогает qtile bar/session.
- **bar** — (part2) палитра бара, отдельный слой.

### Скрипты

- **theme-apply** — применяет слой wall.
  - `theme-apply [IMAGE]` — применить обои
  - `theme-apply --random` — случайные из `$WALLDIR`
  - `theme-apply --last` — повторить последние
  - `theme-apply wall ...` — алиас (part1: то же, что default)
  - Движок: **wallust** (обязателен). 22K-изображения авто-downscale через ffmpeg zimg (ADR-011).
  - **Не делает `qtile reload_config`** — bar/session не меняются.
- **theme-hub** — rofi-хаб выбора обоев (слой wall). Бинди на `Mod+Shift+t`.
- **wal-set** — legacy-обёртка над `theme-apply`.

### State (runtime)

- `~/.local/state/theme-hub/wall.json` — палитра + обои + timestamp + engine (wallust)
- `~/.local/state/theme-hub/last-wall` — путь к последним обоям
- `~/.local/state/theme-hub/prev-wall` — путь к предыдущим обоям (для `--last` fallback)
- `~/.local/state/theme-hub/bar.json` — палитра бара (seed из CYBER_SOLAR_BASE при первом запуске)
- `~/.local/state/theme-hub/wallust.log` — лог wallust (debug)
- `~/.local/state/theme-hub/prepare.log` — лог ffmpeg downscale (debug)
- `~/.cache/wal/colors.json` — pywal-совместимый JSON (для consumers)
- `~/.cache/wal/wal` — путь к последним обоям
- `~/.cache/theme-hub/prepared/` — кэш даунскейленных JPG (для 22K, по sha256)

> **Удалено (мёртвые артефакты предыдущей версии):** `extract-src.jpg`, `last-engine` — больше не пишутся скриптом; удалить вручную при апгрейде.

### Переменные

`THEME_WALLDIR`, `THEME_SATURATION` (0.5), `THEME_ALPHA` (85).
