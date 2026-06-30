---
description: Пайплайн разработки qtile — конфиги, виджеты, хуки, keybindings. planner → qtile-dev → reviewer.
agent: planner
subtask: true
---

# Пайплайн: Qtile разработка

Задача: $ARGUMENTS

## Шаг 1: Анализ

Прочитай `qtile/config.py`, `.opencode/memory/user-profile.md`, `AGENTS.md`.
Оцени: что нужно изменить, какие виджеты/хуки/keybindings затронуть.

## Шаг 2: Проектирование

Сформулируй решение:
- Какие файлы изменить
- Какие API qtile использовать
- Как это повлияет на UX

## Шаг 3: Реализация

Вызови qtile-dev:
```
task(agent="qtile-dev", prompt="Реализуй: $ARGUMENTS. Следуй конвенциям qtile-dev.md. Проверь синтаксис и stow -n.")
```

## Шаг 4: Проверка

Вызови reviewer:
```
task(agent="reviewer", prompt="review: qtile изменения — $ARGUMENTS. Проверь безопасность, стиль, stow-совместимость.")
```

## Шаг 5: Финализация

Если PASS:
- `git add qtile/`
- Покажи diff
- Предложи коммит-месседж: `feat(qtile): <описание>`

Если FAIL:
- Повтори цикл (максимум 3)
