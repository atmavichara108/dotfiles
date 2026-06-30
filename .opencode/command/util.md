---
description: Пайплайн создания утилит — макросы, rofi-меню, btop-темы, wal-схемы. util-dev → reviewer.
agent: builder
subtask: true
---

# Пайплайн: Создание утилиты

Задача: $ARGUMENTS

## Шаг 1: Анализ

Прочитай `.opencode/memory/user-profile.md`, `AGENTS.md`, релевантные конфиги утилит.

## Шаг 2: Реализация

Вызови util-dev:
```
task(agent="util-dev", prompt="Создай утилиту: $ARGUMENTS. Следуй UX-принципам и конвенциям util-dev.md.")
```

## Шаг 3: Проверка

Вызови reviewer:
```
task(agent="reviewer", prompt="review: утилита — $ARGUMENTS. Проверь UX-консистентность, безопасность, stow.")
```

## Шаг 4: Финализация

Если PASS → `git add`, diff, коммит.
Если FAIL → повтор цикла (макс 3).
