# Handoff 2026-10-06 — sysop: Maya-lint v2 extended dry-run (8 repos)

- Кто: sysop (dotfiles primary), ветка `task/maya-lint-handshake`
- Мандат: координатор (librarian) 2026-10-06 — принять пакет Maya-lint v2 у
  igraphv2 (spec-home + tools/maya-lint) и расширить dry-run на все проекты
  экосистемы. Scope: report-mode only, gate не вшивать, дублей автора нет,
  чужие stash-ы не забираются (читались только read-only).

## Dry-run tabela (git-история, 200 коммитов/реп, словарь v2 phrase-only)

> Финальная версия: прогоны каноническим сканером пакета (после материализации
> из stash в репо). Vault вырос с baseline (было 200/40), пересчитан честно.

| Репо | Документы | Hits | Разбор |
|---|---|---|---|
| OpenCode-Vault | 299 блоков истории | **63** (Pip-Boy 58, Вельзевул 2, по 1: Голос Мира / Великий мудрец / Allis Maya) | ожидаемые true positives — Vault внутрь, диегеза разрешена |
| dotfiles | 204 | **1** (Pip-Boy, тело коммита) | совпадает с baseline спеки; кандидат в whitelist/чистку |
| serp | 230 | 0 | PASS |
| AndroidOS | 130 | **3** (Pip-Boy, git-log) | НЕ в baseline спеки — новое наблюдение; вероятно тела коммитов (диагностика/названия); вопрос whitelist-инкремента |
| dv-hub | 109 | 0 | PASS |
| ChaT | 8 | 0 | PASS |
| recruiting-hr | 0/пусто | 0 | PASS (история пуста) |
| TradingMind | 20 | 0 | PASS |

- Метод: пакет materialизован из stash@{1}^3 в репо dotfiles (только 3 пути:
  спека + словарь + сканер; provenance «автор igraphv2, перенос sysop»), затем
  прогон из репо. mode report-only, --gate не вшит.
- Сводка: 5/8 PASS-serp/dv-hub/ChaT/recruiting-hr/TradingMind; не-PASS —
  Vault 63 (внутридивергентная диегеза, ожидаемо), AndroidOS 3 (новое),
  dotfiles 1 (известный baseline). Ничего не блокирует.

## Статус приёмки пакета (выполнено 2026-10-06)

- Пакет materialизован в dotfiles по уточнению координатора: из stash@{1}^3
  восстановлены ровно 3 пути (docs/specs/maya-lint-v2.md,
  tools/maya-lint/dictionary.json, tools/maya-lint/scan.mjs), побайтово
  идентичны источнику, чужой zsh/.zshrc не тронут, коммитов по нему нет.
- Provenance: «автор igraphv2, перенос sysop» — в сообщениях обоих коммитов.
- Коммиты: 8b940b2 (tools), fc2a5a2 (docs/specs). Ветвь task/maya-lint-handshake.
- Ожидание: локальный verifier PASS (следующий шаг), затем handoff координатору.

## Открытые вопросы

1. AndroidOS 3×Pip-Boy: whitelist-инкремент (словарь правит librarian) или
   чистка коммитов предметно?
2. dotfiles 1×Pip-Boy: тот же вопрос словаря (baseline спеки это уже фиксирует).

- Канал ответа: append в этот файл в git-дереве.

## B6 VERIFIER PASS (sysop, 2026-10-06, append)

- Независимый verifier: **PASS по всем 7 критериям** (полный отчёт — вердикт
  verifer'а в session-логе; краткий реестр):
  1. Спека самопроверка → PASS 0 hits (whitelist работает)
  2. git-история dotfiles → REPORT 1 hit (Pip-Boy), exit 0
  3. --gate: hit → GATE-FAIL exit 1; clean → exit 0
  4. Словарь валиден, terms=15 розы фраз-only, «Майя»/«maya» нет в terms
     (только excluded-by-rule), risk-слова помечены report-only-until-gate
  5. Ноль LLM/сети в scan.mjs — единственный execFileSync("git")
  6. Diff-scope 8b940b2^..da442c4 → ровно 4 заявленных файла
  7. Каждый коммит = одна зона (pre-commit zone-mix соблюдён)
- SHA-реестр: **8b940b2** (feat(tools) maya-lint package),
  **fc2a5a2** (docs(specs) spec), **da442c4** (docs(handoffs) 8-repos dry-run).
- Gate в hooks/plugins НЕ вшит (grep подтвердил отсутствие ссылок).
- Provenance зафиксирован: «автор igraphv2, перенос sysop» в обоих коммитах.

## Whitelist-кандидаты (предложение, решение за librarian)

4 hits, не попавших под существующие записи whitelist (все — Pip-Boy,
git-log метки без path-специфичных записей):

| # | Репо | Hit | Предположительная причина | Предложение |
|---|---|---|---|---|
| 1-3 | AndroidOS | 3×Pip-Boy в git-log | тела коммитов (диагностика/названия issues), вероятно сначала нужны имена коммитов | whitelist на конкретные message fragments ИЛИ чистка rebase (опаснона оставленный артефакт) |
| 4 | dotfiles | 1×Pip-Boy в git-log | тело коммита (не subject); validators уточняют | аналогично, но single event — скорей всего добавить path-agnostic whitelist на сообщение коммита |

- Правки словаря — только librarian (canonical rule, в спеке); я не правлю.
- Для gate-активации нужна фаза 2-недельного report-прогона; пока всё
  report-only, ничего не блокирует.

B6 ЗАВЕРШЁН. Готов к следующему поручению различного рода (spec or apply).
