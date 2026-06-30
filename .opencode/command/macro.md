---
description: Пайплайн создания макросов — sxhkd, rofi-меню, горячие клавиши. util-dev → reviewer.
agent: builder
subtask: true
---

# Пайплайн: Создание макросов

Задача: $ARGUMENTS

## Шаг 1: Анализ

Прочитай `rofi/`, `x11/`, `.opencode/memory/user-profile.md`.
Оцени: какие макросы/горячие клавиши нужны.

## Шаг 2: Реализация

Вызови util-dev:
```
task(agent="util-dev", prompt="Создай макросы: $ARGUMENTS. Следуй UX-принципам, проверь консистентность с qtile keybindings.")
```

## Шаг 3: Проверка

Вызови reviewer:
```
task(agent="reviewer", prompt="review: макросы — $ARGUMENTS. Проверь конфликты с qtile, безопасность, stow.")
```

## Шаг 4: Финализация

Если PASS → `git add`, diff, коммит.
Если FAIL → повтор цикла (макс 3).
