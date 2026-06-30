---
description: Пайплайн создания подсказок и чит-шитов. Builder → docs/cheatsheets/.
agent: builder
subtask: true
---

# Пайплайн: Создание чит-шита / подсказки

Задача: $ARGUMENTS

## Шаг 1: Анализ

Прочитай `.opencode/memory/user-profile.md` — пойми, что нужно Максу.
Проверь `docs/cheatsheets/` — нет ли уже похожего.

## Шаг 2: Создание

Создай чит-шит в `docs/cheatsheets/<имя>.md`:
- Формат: markdown, лаконично
- Структура: заголовок → краткое описание → примеры → ссылки
- Без воды, только полезное

## Шаг 3: Финализация

- `git add docs/cheatsheets/<имя>.md`
- Покажи содержимое
- Предложи коммит-месседж: `docs(cheatsheets): <имя>`
