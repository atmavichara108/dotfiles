---
description: Пайплайн настройки уведомлений — dunst, notify-send, скрипты нотификаций. util-dev → reviewer.
agent: builder
subtask: true
---

# Пайплайн: Настройка уведомлений

Задача: $ARGUMENTS

## Шаг 1: Анализ

Прочитай `dunst/dunstrc`, `.opencode/memory/user-profile.md`.
Оцени: что нужно изменить в уведомлениях.

## Шаг 2: Реализация

Вызови util-dev:
```
task(agent="util-dev", prompt="Настрой уведомления: $ARGUMENTS. Проверь dunst-конфиг, визуальную консистентность.")
```

## Шаг 3: Проверка

Вызови reviewer:
```
task(agent="reviewer", prompt="review: уведомления — $ARGUMENTS. Проверь конфиг, безопасность, stow.")
```

## Шаг 4: Финализация

Если PASS → `git add dunst/`, diff, коммит.
Если FAIL → повтор цикла (макс 3).
