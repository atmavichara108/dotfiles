---
type: Pipeline Spec
title: Phase 0 Pipeline Specs — Гигиена dotfiles
description: Пошаговый план исправления всех проблемных мест из аудита.
depends_on: docs/roadmap.md
timestamp: 2026-06-30
---

# Phase 0: Pipeline Specs

> Последовательные пайплайны для исправления всех проблем, найденных в sysaudit.

## Предусловия

```bash
cd /home/rudra/dotfiles
git status                    # чистое working tree
git log --oneline -5          # знать последние коммиты
```

---

## Pipeline 1: Очистка диска

**Агент:** `sysop` (диагностика) → `bash-dev` (скрипты)

### Шаги:

1. **Диагностика** — найти крупные потребители:
   ```bash
   du -sh ~/.cache/* | sort -rh | head -15
   du -sh ~/.local/share/* | sort -rh | head -10
   sudo journalctl --disk-usage
   ```

2. **Очистка** (выполнять с осторожностью):
   - `sudo journalctl --vacuum-time=7d` — логи за 7 дней
   - `paccache -rk2` — оставить 2 последние версии пакетов
   - `paccache -ruk0` — удалить кэш удалённых пакетов
   - `npm cache clean --force` — npm кэш
   - `uv cache clean` — uv кэш
   - `rm -rf ~/.cache/go-build/*` — Go build cache
   - `rm -rf ~/.cargo/registry/*` — Rust registry cache (если >100M)

3. **Проверка результата** — `df -h /` должно показать >10G свободно

**DoD:** После очистки >10G свободно на `/`.

---

## Pipeline 2: Захват дрейфа systemd

**Агент:** `util-dev` → `reviewer`

### Проблема:
`~/.config/systemd/user/` — реальная директория, часть сервисов — обычные файлы,
не под stow. `wal-cycle.*` — уже симлинки, остальные — нет.

### Решение (stow --adopt):

```bash
cd /home/rudra/dotfiles

# Проверить, что будет adopt-нуто
stow --adopt -n systemd 2>&1

# Если всё ОК — adopt
stow --adopt systemd 2>&1

# Перепроверить
stow -n systemd 2>&1
```

### Что будет захвачено:
- `taskchampion-server.service`
- `tmux-tpm-update.service`
- `tmux-tpm-update.timer`
- `default.target.wants/` (если не пусто)
- `timers.target.wants/`

**DoD:** `stow -n systemd` — без ошибок, `git status` показывает новые файлы в `systemd/.config/systemd/user/`.

---

## Pipeline 3: Захват дрейфа wal

**Агент:** `util-dev` → `reviewer`

### Проблема:
`~/.config/wal/` — реальная директория. Только `colors-rofi.rasi` — симлинк.
`colors-dunst`, `colors-polybar.ini` — локальные файлы, не в репо.

### Решение:

```bash
cd /home/rudra/dotfiles

# Проверить
stow --adopt -n wal 2>&1

# Adopt
stow --adopt wal 2>&1

# Проверить
stow -n wal 2>&1
```

**Важно:** `~/.config/wal/colorschemes/` — runtime-данные pywal, НЕ включать в репо.
Добавить в `.gitignore` пакета wal: `colorschemes/`.

**DoD:** `stow -n wal` — без ошибок. Шаблоны в репо. `colorschemes/` в `.gitignore`.

---

## Pipeline 4: Добавление gtk-4.0

**Агент:** `util-dev` → `reviewer`

### Проблема:
`~/.config/gtk-4.0/gtk.css` — обычный файл, не совпадает с gtk-3.0 версией.
Пакет `gtk` управляет только gtk-3.0.

### Решение — расширить пакет `gtk`:

```bash
cd /home/rudra/dotfiles

# Создать структуру gtk-4.0
mkdir -p gtk/.config/gtk-4.0

# Скопировать текущий gtk.css из системы
cp /home/rudra/.config/gtk-4.0/gtk.css gtk/.config/gtk-4.0/gtk.css

# Применить stow --adopt (синхронизирует)
stow --adopt -n gtk   # проверить
stow --adopt gtk      # выполнить

# Проверить
stow -n gtk
```

**Или** — скопировать gtk-3.0 gtk.css в gtk-4.0 (если нужно одинаково):
```bash
cp gtk/.config/gtk-3.0/gtk.css gtk/.config/gtk-4.0/gtk.css
```

**DoD:** `~/.config/gtk-4.0/gtk.css` — симлинк в dotfiles. `stow -n gtk` — без ошибок.

---

## Pipeline 5: Приведение picom к единой структуре

**Агент:** `util-dev` → `reviewer`

### Проблема:
picom имеет двойную структуру:
- `~/.config/picom/` (пустая директория) — симлинк на `dotfiles/picom/.config/picom/`
- `~/.config/picom.conf` — симлинк на `dotfiles/picom/.config/picom.conf`

### Решение:
picom читает из `~/.config/picom.conf` или `~/.config/picom/picom.conf`.
Двойная структура — костыль. Выбрать единый стандарт.

**Вариант А (проще):** Оставить как есть, удалить пустую директорию picom.
```bash
cd /home/rudra/dotfiles
stow -D picom                # удалить симлинки
rmdir picom/.config/picom    # удалить пустую директорию
stow picom                   # переустановить
```

**Вариант Б (правильнее):** Перенести picom.conf внутрь директории.
```bash
cd /home/rudra/dotfiles
stow -D picom
mv picom/.config/{picom.conf,picom/picom.conf}
rm -f /home/rudra/.config/picom.conf
stow picom
```

### Требуется решение от Макса.

**DoD:** `stow -n picom` — без ошибок. Единая структура: либо `picom.conf` (файл), либо `picom/picom.conf` (в директории).

---

## Pipeline 6: Приведение nvim к stow-стандарту (опционально)

**Агент:** `util-dev` → `reviewer`

### Проблема:
`~/.config/nvim/` — реальная директория. Все файлы внутри — симлинки на dotfiles.
Stow не создавал эту директорию — она создана вручную или скриптом.

### Решение:

```bash
cd /home/rudra/dotfiles

# ВАЖНО: проверить, что dotfiles/nvim/.config/nvim содержит всё актуальное
diff -r ~/.config/nvim/ nvim/.config/nvim/

# Если различий нет — пересоздать чистый симлинк
rm -rf ~/.config/nvim
stow -n nvim    # проверить
stow nvim       # выполнить
```

**Если есть различия** — сначала `stow --adopt nvim`, потом чистый stow.

**DoD:** `~/.config/nvim` — симлинк на `dotfiles/nvim/.config/nvim`.

---

## Pipeline 7: Чистка picom stub и скриптов бэкапа

**Агент:** `util-dev`

### Найти и почистить:
```bash
# gtk.css.backup — остаток ручного бэкапа
rm /home/rudra/.config/gtk-3.0/gtk.css.backup
rm /home/rudra/.config/gtk-4.0/gtk.css.backup
if [ -f /home/rudra/.config/gtk-3.0/gtk.css.bak ]; then rm /home/rudra/.config/gtk-3.0/gtk.css.bak; fi

# rofi.backup-20260223-193632 — старый симлинк, мусор
stow -D rofi 2>/dev/null
rm -f /home/rudra/.config/rofi.backup-20260223-193632
rm -rf /home/rudra/.config/rofi.backup-20260223-193632
stow rofi
```

**DoD:** В `~/.config/` нет `*.backup*`, `*.bak` файлов, если они не нужны.

---

## Pipeline 8: Обновление .gitignore для wal

**Агент:** `builder` → `reviewer`

### Добавить в `wal/.gitignore`:
```
colorschemes/
*.pyc
__pycache__/
```

**DoD:** `wal/.gitignore` создан/обновлён. Runtime-данные pywal не трекаются.

---

## Последовательность запуска

```
Pipeline 1 (Очистка диска)
    ↓
Pipeline 2 (systemd adopt)
    ↓
Pipeline 3 (wal adopt) + Pipeline 4 (gtk-4.0) + Pipeline 8 (.gitignore wal)  — параллельно
    ↓
Pipeline 5 (picom) + Pipeline 6 (nvim)  — параллельно, после ответа Макса
    ↓
Pipeline 7 (чистка бэкапов)
    ↓
git commit -m "chore: phase0 — fix config drift and cleanup"
```

## Команда запуска

```bash
# Запустить все пайплайны Phase 0 последовательно
task(agent="builder", prompt="Выполнить Phase 0 pipelines согласно docs/pipelines-phase0.md. Начать с Pipeline 1, после завершения каждого переходить к следующему. После Pipeline 3 и 8 дождаться параллельных Pipeline 4, 5, 6 (зависит от ответа Макса). По завершению всех — сделать git commit.")
```
