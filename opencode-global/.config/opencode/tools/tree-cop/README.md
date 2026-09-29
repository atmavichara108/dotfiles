# tools/tree-cop — коп чистоты дерева

**Зачем.** Параллельные сессии делят одно рабочее дерево. Каждый раз, когда
агент вручную решает «моё это или чужое», он тратит токены и ошибается.
Коп делает эту работу кодом: одна команда — один вердикт.

**Кредо.** Классификация грязи, атрибуция mine/foreign, невидимая грязь
(skip-worktree, mode), отставание от origin/main, именованный stash только
чужего. Всё это — работа скрипта, не модели.

## Команды

```bash
# Вердикт для текущей сессии (--mine можно префиксом каталога)
.venv/bin/python tools/tree-cop/tree-cop.py status --mine tools/agent-ops --mine 04-Memory/facts.md

# Те же гейты, что и шаг 0 /ship
.venv/bin/python tools/tree-cop/tree-cop.py ship-check --mine <...>

# Убрать ТОЛЬКО чужое (своё остаётся в дереве), затем pop после операции
.venv/bin/python tools/tree-cop/tree-cop.py stash-foreign --mine <...> -m "tree-cop: <причина>"
.venv/bin/python tools/tree-cop/tree-cop.py pop
```

Вывод — одна строка JSON:

```json
{"ok": true, "verdict": "STOP", "branch": "task/x", "mine": [...], "foreign": [...],
 "skip_worktree": [...], "mode_changes": [...],
 "origin_main": {"ahead": 0, "behind": 2}, "reasons": [...]}
```

Exit: `0` = GO, `1` = STOP/ошибка.

## Атрибуция

- tracked-изменение: своё iff путь попал в `--mine` (равенство или префикс + `/`);
- untracked: то же правило;
- всё, что не попало в `--mine`, — **чужое** (чужая грязь = STOP);
- skip-worktree (`S`/`s` в `git ls-files -v`) и mode-правки — невидимая грязь,
  докладываются отдельными полями: именно из-за неё ломаются «неожиданные»
  `git add` и пропавшие правки.

## Агент

`.opencode/agent/tree-cop.md` (режиссёр): первый шаг — вызвать коп, дальше
действовать по вердикту. Никогда не дублирует работу скрипта руками.
Запреты: `reset --hard`, `checkout --`, `clean -fd`, `--force`, `--no-verify`,
редактировать чужие файлы, бесхозные stash.

## Тесты

```bash
.venv/bin/python -m pytest tools/tree-cop/tests/ -q   # 14 тестов, офлайн
```

Покрыты: обе формы porcelain (` M path` / `M  path`), rename `a -> b`, untracked,
префиксная и слэш-нормализация атрибуции, skip-worktree, mode-change,
вердикты GO/STOP, stash только чужих путей (своё не попадает).

## Вшивка

`/ship` (dotfiles) шаг 0 — вызов `ship-check` вместо ручного preflight;
шаг 3 — `stash-foreign`/`pop` для своей грязи.

## Запреты

Коп ничего не коммитит, не пушит и не удаляет. Он только читает состояние,
и по прямой команде делает `stash push -- <чужие пути>` / `stash pop`.
