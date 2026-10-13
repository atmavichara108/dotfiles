---
description: Preflight версионирования vflight — STOP/GO текущего репо, full (память-drill), кросс-репо стейт. Только статус, ничего не меняет.
agent: sysop
subtask: true
---

# /vflight — preflight версионирования (И-30 Волна 3)

Инструмент: `scripts/.local/bin/vflight`. Аргументы: $ARGUMENTS
Режим выбирается по первому слову аргументов (пусто = preflight).

## Жёсткие запреты

- **vflight НИКОГДА сам не коммитит, не пушит, не мержит, не чистит дерево, не
  трогает чужие правки** (никаких `stash-foreign`, `checkout`, `reset`). Он —
  только статус-гейт: вердикт + причины. Все изменяющие операции — отдельный
  штатный маршрут (tree-cop, primary, git-пайплайн) и только после явного
  решения primary.
- Только метаданные: пути, счётчики, вердикты. Содержимое файлов не читается
  и не печатается; секрет-подобные пути маскируются автоматически.

## Режимы

### `/vflight` — preflight текущего репо (freed + tree-cop)

```
vflight [--mine <свой-префикс>]...
```

Прогнать preflight, human-отчёт primary: freed check, tree-cop ship-check
(чужие пути, origin/main ahead/behind), вердикт GO/STOP + причины.
Exit: 0=GO, 1=STOP, 2=внутренняя ошибка.

### `/vflight full` — preflight + гейт памяти (часть B)

```
vflight full [--mine <свой-префикс>]...
```

То же + `memscan --drill` (exit≠0 → STOP «состояние не выживает»). Порядок
версии: preflight → зоны → коммит → память (drill) → merge; ADR-решения на
каждом шаге принимает primary, не auto.

### `/vflight repo <path>` — кросс-репо стейт (часть C)

```
vflight repo <path> [--json] [--no-fetch]
```

Универсальный preflight для ЛЮБОГО git-репо (Vault, SSA, future): fetch
origin (только remote-tracking refs, если есть; `--no-fetch` — пассивно),
dirty-count (staged/unstaged/untracked), ahead/behind, конфликт-маркеры,
MERGE_HEAD. Вердикт **CLEAN/DIRTY** + `accepts_dirty_work` (может ли репо
принимать новую работу: дерево чистое, merge не висит, behind=0).
Exit: 0=CLEAN, 1=DIRTY, 2=не репо/ошибка.

## Пайплайн команды

1. Выполнить выбранный режим bash-ом (не через субагента — это дешёвый
   детерминированный скрипт).
2. Доложить primary: вердикт + причины одной строкой; STOP — перечислить
   причины списком. При STOP — дальше ничего не делать, решение за primary.
3. При `repo` на нескольких репо — прогнать каждый путь отдельно, свести в
   таблицу путь → вердикт → может принимать работу.
