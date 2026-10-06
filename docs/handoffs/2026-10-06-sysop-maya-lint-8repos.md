# Handoff 2026-10-06 — sysop: Maya-lint v2 extended dry-run (8 repos)

- Кто: sysop (dotfiles primary), ветка `task/maya-lint-handshake`
- Мандат: координатор (librarian) 2026-10-06 — принять пакет Maya-lint v2 у
  igraphv2 (spec-home + tools/maya-lint) и расширить dry-run на все проекты
  экосистемы. Scope: report-mode only, gate не вшивать, дублей автора нет,
  чужие stash-ы не забираются (читались только read-only).

## Dry-run tabela (git-история, 200 коммитов/реп, словарь v2 phrase-only)

| Репо | Документы | Hits | Разбор |
|---|---|---|---|
| OpenCode-Vault | 200 | **40** (по факту отчёта 40 строк hits: Pip-Boy, Вельзевул, Голос Мира, Великий мудрец, Allis Maya) | ожидаемые true positives — Vault внутрь, диегеза разрешена |
| dotfiles | 204 | **1** (Pip-Boy, тело коммита) | совпадает с baseline спеки; кандидат в whitelist/чистку |
| serp | 230 | 0 | PASS |
| AndroidOS | (200) | **3** (Pip-Boy, git-log) | не в baseline спеки — новые данные; вероятно тело коммита (диагностика/названия), кандидат в whitelist предметно |
| dv-hub | 109 | 0 | PASS |
| ChaT | 8 | 0 | PASS |
| recruiting-hr | 0/пусто | 0 | PASS (история пуста) |
| TradingMind | 20 | 0 | PASS |

- Метод: scan.mjs из stash@{1}^3 (read-only, владелец igraphv2), временная
  папка /tmp/opencode/maya-lint-check; модификация файлов автором/репо — ноль.
- Сводка: 7/8 гит-историй чистые или ожидаемо-диегетические; не-PASS:
  Vault (ожидаемо) + AndroidOS 3×Pip-Boy (новое наблюдение) + dotfiles 1
  (известный). report-mode only — ничего не блокирует.

## Статус приёмки пакета (запрос автору отправлен через координатора)

- Пакет (спека + словарь + сканер) согласно канону принадлежит автору igraphv2;
  перенос в dotfiles как владелец репо — после явной передачи автором
  (provenance: «автор igraphv2, перенос sysop»), не из чужого stash.
- Если автор не доступен — BLOCKED пункт приёмки отдельно, dry-run выше от
  этого не зависит (проверка была на read-only-копии из stash по разрешению
  координатора).

## Открытые вопросы

1. AndroidOS 3×Pip-Boy: whitelist-инкремент (словарь правит librarian) или
   чистка коммитов предметно?
2. dotfiles 1×Pip-Boy: тот же вопрос словаря (baseline спеки это уже фиксирует).

- Канал ответа: append в этот файл в git-дереве.
