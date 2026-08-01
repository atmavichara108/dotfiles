# Эстетика dotfiles — cyberpunk ∩ solarpunk

> Короткий указатель для агентов. Полная версия: ADR-009 + ADR-010 в `docs/decisions.md`.

## Доктрина

**Cyberpunk ∩ solarpunk** — высокотехнологично и плавно, но открыто и «живое».
Без мрачного гротеска. Без корпоративного глянца.

## Принципы

- **Минимализм + hi-tech** — лёгкие UI (rofi/dunst/qtile), без тяжёлых GUI
- **Скорость = часть эстетики** — задержка apply = дефект UX
- **Слои theming** — wall ≠ bar ≠ apps; не один random на всё
- **Motion** — короткие уместные анимации (fade/flash), не декоративный шум
- **Тёмная база** + solarpunk-акценты (тепло/зелень/янтарь) точечно

## Anti-patterns

- DoomOne и чужие fallback-палитры «на всякий случай»
- Webkit-тяжёлые theme apps (aether-класс) как runtime-зависимость
- Skeuomorphism, excess gloss
- `reload_config` для смены цветов бара — только live refresh

## Связь с S2

- Engine: wallust (fast), pywal optional fallback (ADR-010)
- Слои: `wall` | `bar` | `apps` (targets.toml)
- Бар: live `refresh_bar_colors`, без reload_config
- Fallback: last known-good из `~/.local/state/theme-hub/` или cyber-solar base palette

## Для агентов

Перед любой кастомизацией UI (rofi/dunst/qtile bar/picom) — читай ADR-009.
Перед правкой theme-engine — читай ADR-010.
