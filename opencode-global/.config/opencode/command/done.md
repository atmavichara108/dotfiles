---
description: Протокол завершения задачи — авто-документирование по memory-model проекта, затем /commit.
model: opencode-go/deepseek-v4-flash
---
# Протокол завершения задачи

Когда задача из TASKS.md выполнена, определи memory-model проекта и выполни
соответствующий чеклист. НЕ предполагай наличие vault-сущностей по умолчанию.

## 0. Определи memory-model

- **vault-based** — в корне проекта есть `04-Memory/` (или это сам vault-репо с
  `00-INDEX.md`, `02-Methods/`, `03-Projects/`). Пример: OpenCode-Vault.
- **docs-based** — есть `docs/` (`decisions.md`, `progress.md`, `techdebt.md`),
  локальный `TASKS.md`/`AGENTS.md` в корне, но нет `04-Memory/`. Пример: SERPlux.
- Если ни того, ни другого — действуй по docs-based fallback: обнови локальный
  `TASKS.md`/`README.md`/`CHANGELOG.md`, пропусти vault/docs-спец шаги.

Если модель неоднозначна — спроси пользователя явно, не угадывай.

## Чеклист (vault-based)

1. **TASKS.md** — перенеси строку задачи из Active/Planned в Done, укажи дату.
2. **Описать созданное** — зафиксируй результат в соответствующем месте волта:
   - Новая команда → `01-Reference/commands.md`
   - Новый метод → `02-Methods/<method>.md` + ссылка в `00-INDEX.md`
   - Новый факт → `01-Reference/<раздел>.md` или `04-Memory/facts.md`
   - Изменение в проекте → карточка `03-Projects/<project>.md`
3. **VibeOS** — обнови осмысленно ЕСЛИ задача повлияла на философию/методы/принципы.
   Если нет — напиши: «VibeOS: без изменений».
4. **active-context.md** — обнови `04-Memory/active-context.md`: убери выполненное,
   добавь следующее из Planned.
5. **/commit** — закоммить изменения (см. секцию про /commit ниже).

## Чеклист (docs-based)

1. **TASKS.md** (локальный) — перенеси задачу в Done, дату. Если локального TASKS нет —
   обнови `CHANGELOG.md` или `README.md`.
2. **Статус → `docs/progress.md`** — что сделано, что в работе, что дальше. Кратко.
3. **Решение → `docs/decisions.md`** — ЕСЛИ принято архитектурное решение (ADR):
   дата, проблема, решение, следствия. Иначе пропусти.
4. **Техдолг/блокеры → `docs/techdebt.md`** — ЕСЛИ всплыли. Иначе пропуши.
5. **/commit** — закоммить изменения (см. секцию про /commit ниже).

Не требуй `04-Memory/`, VibeOS, `00-INDEX.md`, `03-Projects/` — их нет в docs-based проектах.

## /commit dependency

`/done` делегирует финальный коммит проектной команде `/commit`, если она
определена в `.opencode/command/commit.md` (project-level) или глобально.
Перед вызовом проверь, что `/commit` доступен в текущем проекте; если нет —
остановись и сообщи, что нужен commit-команда или ручной коммит.
НЕ предполагай, что verifier/`commit-guard` уже отработал — gate `verify=PASS →
finalize` отдельный unresolved контракт (T-089), `/done` его не гарантирует.

## Отчёт

В конце выведи краткий отчёт:
- [ ] Memory-model: vault-based / docs-based / fallback
- [ ] TASKS.md (локальный): обновлён / не требовался
- [ ] Документация: <пути> / не требовалась
- [ ] VibeOS (только vault): обновлён / без изменений / н/д
- [ ] active-context (только vault): обновлён / н/д
- [ ] decisions/techdebt (только docs): обновлены / не требовались / н/д
- [ ] /commit: вызван / недоступен (причина) / отложен пользователем