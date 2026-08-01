---
type: Tech Debt Registry
title: Технический долг — dotfiles
description: Зафиксированные уроки и правила по техдолгу.
timestamp: 2026-07-31
---

# Технический долг — dotfiles

---

### TD-001: Эффективность кода и агентной работы (theme-hub incident)
**Дата:** 2026-07-31 (обновлено 2026-08-02)
**Суть:** «Оптимизации» theme-apply (magick resize + thumb + сложный fallback) ухудшили UX: выше CPU/GPU/temp, медленнее выбор обоев. Больше кода ≠ лучше.
**Правило:**
- Hot path = минимум syscalls и декодов изображений
- Не добавлять «ускорители» без замера; один decode на apply max (engine only)
- Предпочитать удаление работы добавлению кэшей/препроцессинга
- Агенты: маленькие диффы, измеримый DoD, не жечь токены на слои абстракций
- Стиль: профессиональный, lean, в духе ADR-009 (скорость = эстетика)
**Триггер:** любой performance-pass по theme/rofi/qtile; code review агентов

**Резолюция (2026-08-02) — Part 1 S2:**
- **Code efficiency:** theme-apply 207 → 169 строк; извлечены helpers (`prepare_image`, `update_state`, `extract_palette`, `read_prev_wallpaper`, `resolve_image`); DRY применён.
- **State management:** state-drift устранён — `--last` теперь синхронизирует `wall.json` через `update_state` (раньше только main-путь писал state).
- **Memory:** ffmpeg streaming (zimg) устраняет OOM на 22K — константная память независимо от размера исходника (ADR-011). magick resize убран полностью.
- **Next:** мониторить Part 2 S2 (bar layer) на аналогичные паттерны — не допустить повторного разрастания hot path.
