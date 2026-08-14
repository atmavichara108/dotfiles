---
type: Tech Debt Registry
title: Технический долг — dotfiles
description: Зафиксированные уроки и правила по техдолгу.
timestamp: 2026-07-31
---

# Технический долг — dotfiles

---

### TD-001: Эффективность кода и агентной работы (theme-hub incident)
**Дата:** 2026-07-31 (обновлено 2026-08-02, 2026-08-14)
**Суть:** «Оптимизации» theme-apply (magick resize + thumb + сложный fallback) ухудшили UX: выше CPU/GPU/temp, медленнее выбор обоев. Больше кода ≠ лучше.
**Правило:**
- Hot path = минимум syscalls и декодов изображений
- Не добавлять «ускорители» без замера; один decode на apply max (engine only)
- Предпочитать удаление работы добавлению кэшей/препроцессинга
- Агенты: маленькие диффы, измеримый DoD, не жечь токены на слои абстракций
- Стиль: профессиональный, lean, в духе ADR-009 (скорость = эстетика)
**Триггер:** любой performance-pass по theme/rofi/qtile; code review агентов

**Резолюция (2026-08-02) — Part 1 S2:**
- **Code efficiency:** theme-apply 207 → 169 строк (рефакторинг 183801b), но после palette cache и flock вырос до ~355 (678784b, 839cbba). Извлечены helpers (`prepare_image`, `update_state`, `extract_palette`, `read_prev_wallpaper`, `resolve_image`, `check/save/restore_palette_cache`); DRY применён.
- **State management:** state-drift устранён — `--last` теперь синхронизирует `wall.json` через `update_state` (раньше только main-путь писал state).
- **Memory (компромисс):** magick НЕ убран полностью — он используется для downscale 22K (`magick -resize 3840x2160>`, ADR-011). zimg/ffmpeg отвергнут (недоступен в Manjaro, BUG-001). Пик памяти высок на **первом** prepare, повторные apply — cache hits (PNG prepared + palette cache).
- **Остаточный долг:** оптимизация первого downscale 22K — magick не streaming; варианты: более лёгкий rescale / параллельная подготовка / JPEG XL.
- **Residual risk (обязательный DoD до merge):** concurrent runtime test был ограничен permissions — сериализация через flock (839cbba, 1a2230d) не проверена при реальном параллельном apply; тест обязателен до merge, если ещё не прошёл.
- **Next:** мониторить Part 2 S2 (bar layer) на аналогичные паттерны — не допустить повторного разрастания hot path.
