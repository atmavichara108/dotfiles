# Handoff — Sysop → Дирижёр: garbage-guard (защита от decode-мусора моделей)

**Дата:** 2026-10-07
**Ветка:** task/garbage-guard (база main=bb15ced)
**Автор:** sysop (primary)
**Мандат:** GO Дирижёра по форензик-плану; подтверждение Рудры provenance
msg_117add5b50018qevDS0UqIaBUF (ses_eedd28c4…, 21:43:50) — сверен Дирижёром
по sqlite. Башенный контроль соблюдён: letter.sh канон B15 (без -m, единственная
точка) не тронут; receipts-журнал B18 не дублируется (REFUSE происходит ДО
записи sent).

---

## Реализация (zero-LLM, детерминированно)

| Компонент | Что делает |
|---|---|
| `tools/garbage-guard/guard.py` | Детектор CJK/kana/Hangul/Thai/FFFD. Команды: `scan --staged` (pre-commit), `scan --path …` (sweep), `check-text` (stdin, letter.sh). Exit 0/1/2. |
| `tools/garbage-guard/config.json` | Whitlist fragment-level (по образцу maya-lint) + `exclude_prefixes` (node_modules, powerlevel10k — легальный CJK-контент вендора). |
| pre-commit **гейт 6** | staged через guard; обход `MOJIBAKE_OK=1`. |
| `letter.sh` garbage-гейт | REFUSE **exit 4** при rc=1 guard'а (мусор); rc=2 (ошибка инструмента) — не блокирует; обход `GARBAGE_OK=1`. Проверка ДО journal-append и до run. |
| `.opencode/memory/decisions.md` | Запись инцидента: symptom→repro→root cause→damage→fix→evidence→статус. |

Whitelist-кейсы: CJK-артефакт 2d9f5c2 (2 иероглифа, чужая зона), иероглифы в tmux-open,
осознанный контент), memory-запись инцидента (содержит CJK-доказательства).
Само-исключение: guard/config не проверяются самим собой (иначе self-eating).

## Приёмка (6/6, реальный прогон)

1. positive (мусорный текст инцидента) → rc=1 ✓
2. negative (чистый ру-ен текст) → rc=0 ✓
3. whitelist-файлы (`多久` в hello-handoff, `命名` в tmux-open) → rc=0 ✓
4. тот же артефакт вне whitelist → rc=1 ✓
5. letter.sh: мусорное письмо → **REFUSE exit 4, журнал не тронут** ✓
6. full-tree sweep (`scan --path .`) → rc=0 (whitelist+исключения покрыли всё
   легальное); staged-скан guard-файлов → rc=0; регрессия smoke.sh 15/15 ✓

Живое подтверждение гейта: коммит memory-записи был заблокирован самим гейтом 6
(запись содержит CJK-доказательства) → whitelist-фрагменты добавлены → прошёл.
Зоны: три коммита по зонам (tools/misc, githooks+memory/opencode), гейт зоны-микс
отработал штатно.

## Repro

```bash
cd ~/dotfiles && git switch task/garbage-guard
python3 tools/garbage-guard/guard.py check-text <<< 'мусор <CJK-символ>'     # rc=1
python3 tools/garbage-guard/guard.py check-text <<< 'чистый текст'           # rc=0
python3 tools/garbage-guard/guard.py scan --path .                           # rc=0
bash tools/peer-comms/letter.sh --to ses_x --text 'мусор <CJK>' --scope t    # exit 4
(реальные positive-кейсы: /tmp/opencode/gg-neg.md, msg_116a1f92… в opencode.db)
```

## Артефакты

| Артефакт | SHA |
|---|---|
| guard.py + config.json + letter.sh гейт | `2c9e581` |
| whitelist-фрагменты memory | `dcd5c82` |
| pre-commit гейт 6 + запись инцидента | `ca4bf3c` |
| handoff | этот коммит |

Дрейд-факт: при работе ветка дважды уезжала под общим HEAD (чужие
`task/next-20261007-2215`) — B22-механизм (claim/release) использован штатно.
