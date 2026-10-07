# Handoff — Sysop → Дирижёр: garbage-guard latin-класс (A-Za-z-вставки в кириллицу)

**Дата:** 2026-10-07
**Ветка:** task/latin-guard (база main=44e909a)
**Автор:** sysop (primary)
**Мандат:** «очередь garbage-guard-у — латинический класс» (Дирижёр, 07.10, не горящее)

---

## Решение «насколько сложно»: несложно, сделано за один заход

Метод как с CJK: сначала данные. Полный скан трекаемого дерева на соседство
кириллица↔латиница (без разделителей) дал **12 кандидатов** — все проверены
вручную: 10 реальных оптифайлов (гомоглифы-вставки в слова вроде «agent»,
«hello», «копа», «Смонтировано», «гейтов», «материализован», «librarian»,
«свой», «deno» — латинскими буквами внутри кириллицы, см. диффы коммитов)
+ 2 спорных. Порог ложных на
естественном code-switching — ноль: токен-правило (буквенная цепочка без
пробела/дефиса/слэша, содержащая ОБА скрипта) не трогает `letter.sh`, `task/*`,
hyphen-связки; escape-последовательности (`\nЗ`) исключены.

## Реализация

- `guard.py`: `find_latin_mix` — токен-правило (см. коммит), общий whitelist
  span-механизм, тот же exit-контур. Порогов эвристики нет — структурное
  правило, не статистика.
- Оптикфайлы в **своих** зонах (6 файлов): head-guard.sh, maya-lint dict,
  disk-hygiene, ai-syshelp.py, memory/decisions.md, telemetry.ts, + 3 своих
  handoff (включая чистку CJK-цитат из своего garbage-guard handoff).
- **Не тронуты** (чужие тексты): `docs/specs/mailing-protocol-proto.md`
  (смешение скриптов в исходном тексте автора) — whitelist-фрагмент.

## Приёмка (7/7)

1. positive (латиница-вставки в кириллические слова, 3 кейса) → rc=1 ✓
2. negative code-switching (`letter.sh`, `task/*`, hyphen) → rc=0 ✓
3. negative escape (`\nЗапусти`) → rc=0 ✓
4. 4 реальных письма этой недели → rc=0 (ноль ложных на живой прозе) ✓
5. whitelist спеки igraphv2 → rc=0 без правки чужого текста ✓
6. full-tree sweep → rc=0 (чисто, включая новые оптифайлы) ✓
7. letter.sh-цепочка: check-text rc=1 на гомоглифе → REFUSE exit 4 (тот же
   вызов, что в B18-контуре) ✓

## Repro

```bash
cd ~/dotfiles && git switch task/latin-guard
printf 'аГЕНТ вставк' | python3 tools/garbage-guard/guard.py check-text  # rc=1 (латиница в кириллице)
printf 'запусти letter.sh на task/ветке fine' | python3 tools/garbage-guard/guard.py check-text  # rc=0
python3 tools/garbage-guard/guard.py scan --path .                                               # rc=0
```

## Артефакты

| Артефакт | SHA |
|---|---|
| guard.py latin-класс + config whitelist + оптифайлы своих тулз | `d0fb06d` |
| scripts оптифайлы | `c641c5d` |
| opencode-зона оптифайлы (memory, telemetry) | `7150b76` |
| handoff-оптифайлы | `3d540cb` |
| handoff | этот коммит |

Замечание: коммиты проходили через уже живой гейт 6 с новым классом — каждая
зона чиста по обеим классам (CJK + latin).
