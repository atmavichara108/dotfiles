---
description: Пайплайн создания/изменения bash-скриптов. bash-dev → reviewer. Аргумент: описание скрипта.
agent: builder
subtask: true
---

# Пайплайн: Создание скрипта

Задача: $ARGUMENTS

## Шаг 1: Проектирование

Прочитай `.opencode/memory/user-profile.md` и `AGENTS.md`.
Сформулируй, что скрипт должен делать, какие входные/выходные данные.

## Шаг 2: Реализация

Вызови bash-dev:
```
task(agent="bash-dev", prompt="Создай скрипт: $ARGUMENTS. Strict mode, обработка ошибок, dry-run флаг если нужно. Положи в scripts/.")
```

## Шаг 3: Проверка

После реализации вызови reviewer:
```
task(agent="reviewer", prompt="review: новый скрипт — $ARGUMENTS. Проверь безопасность, стиль, strict mode.")
```

## Шаг 4: Финализация

Если PASS:
- `chmod +x scripts/<script>.sh`
- `git add scripts/<script>.sh`
- Покажи diff и краткое описание
- Предложи коммит-месседж: `feat(scripts): <описание>`

Если FAIL:
- Передай замечания reviewer обратно в bash-dev
- Повтори шаг 2-3 (максимум 3 цикла)
