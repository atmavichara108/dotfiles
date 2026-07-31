# scripts

Скрипты в `~/.local/bin/` через GNU Stow (`stow scripts`).

## Темы (S2 aether-lite)

- **theme-apply** — pywal + обои + reload стека.
  - `theme-apply [IMAGE]` — применить обои
  - `theme-apply --random` — случайные из `$WALLDIR`
  - `theme-apply --last` — повторить последние
- **theme-hub** — rofi-хаб выбора тем/обоев. Бинди на `Mod+Shift+t`.
- **wal-set** — legacy-обёрка над `theme-apply`.

Переменные: `THEME_WALLDIR`, `THEME_SATURATION` (0.5), `THEME_ALPHA` (85).
