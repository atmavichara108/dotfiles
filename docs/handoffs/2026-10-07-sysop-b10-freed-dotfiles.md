# Handoff — Sysop → Дирижёр: B10 Git Freed kernel-детектор в dotfiles

**Дата:** 2026-10-07
**Ветка:** task/git-freed-b10 (dotfiles, от 43b5258)
**Автор:** sysop (primary)
**Scope:** B10 — перенос детектора freed.py из волта (паттерн-режим acc6023) в
dotfiles. Прод-сессии и `.mcode` не трогались.

---

## Перенос

**Источник:** `/home/rudra/Projects/OpenCode-Vault/tools/git-agent/freed.py`
(243 строки; паттерн-режим common-field + `common_health` из acc6023).
**Цель:** `tools/git-agent/freed.py` в dotfiles (265 строк, коммит `7e98909`).

**Адаптации под dotfiles (и только они):**

| Что | Волт | Dotfiles |
|---|---|---|
| CLAIMS | `tools/peers/generated/claims.jsonl` (`op: claim/release`) | `tools/peer-comms/claims.jsonl` (`op: hello/ack/bye`) |
| fold leases | claim без позднего release | последняя запись сессии != bye, TTL из записи (`ttl_minutes`, дефолт 30 мин) |
| Классификация | common_field_dirty / junk / tracked_dirty / untracked | **common_field_dirty / routine_tracked / guest_untracked / junk_candidates** (требование мандата: различение routine/common-field/lease/guest) |
| detect | — | + ключ `repo` (имя репо, для kernel-сигнала) |

**Без изменений:** COMMON_DIR = `04-Memory/idea-graph`, паттерн-режим
(`is_common_field` — любой `*.jsonl` рекурсивно, кроме `archive`/`_archive` —
контракт git-freed.md S5), `common_health` (dup-id / bad-json), exit-семантика
`check` 0/1/2, main-щит, merge-state блоки, `--untracked-files=all`.

Сверено с `git-freed.md S5/S8.1` (волт, 93ae751): оба обязательных кейса
(гонка в подкаталоге + дубль id) воспроизводятся.

## Приёмка (реальный прогон, dotfiles-материал)

### A. Sandbox-гонка двух писателей → WARN common-field + rc=1

Sandbox: `04-Memory/idea-graph/race-test/` (контрольная песочница; после снятия
evidence перемещена в `/tmp/opencode/b10-sandbox-evidence/`, в дерево прод не ушла).

Файлы: `race-nodes.jsonl` (3 строки: writer A `b10-a-001`, writer B `b10-b-001`,
контрольный дубль `b10-a-001` (конфликтный кейс append-new-ID)) + `_archive/race-nodes.jsonl`
(двойной `b10-arch-dup` — негативный контроль исключения архива).

- `freed.py check` →
  `WARN: common-field:04-Memory/idea-graph/race-test/race-nodes.jsonl; dup-id:04-Memory/idea-graph/race-test/race-nodes.jsonl:b10-a-001` → **rc=1** ✓
- `_archive/race-nodes.jsonl` дал **0 warnings** — исключение архива работает ✓
- detect JSON: `common_field_dirty=[race-nodes.jsonl]`,
  `common_health=[dup-id:...:b10-a-001]`, `warnings=2`, `blocked=[]`, `ok=true`.

### B. Чистое рутинное дерево → тихий GO

После уборки песочницы: `OK: no blocks (dirty_count=3, branch=task/git-freed-b10)` → **rc=0** ✓

### C. Прод-режим: ноль ложных срабатываний

Дерево dotfiles (обычный контур): чужие `M opencode-global/.config/opencode/opencode.jsonc`
(= routine_tracked), `?? shim/` (= guest_untracked), `?? tools/git-agent/`
(= guest) — **warnings=[], ok=true, rc=0** ✓. `lease-list` → `no active leases`
(оба claims > TTL=30 мин, `fresh: false`) — нет ложных lease-варнингов ✓.

## Repro

```bash
cd ~/dotfiles
python3 tools/git-agent/freed.py check   # прод: rc=0
# sandbox-гонка:
mkdir -p 04-Memory/idea-graph/race-test/_archive
printf '%s\n' '{"id":"b10-a-001","status":"raw"}' '{"id":"b10-b-001","status":"raw"}' \
  '{"id":"b10-a-001","status":"raw"}' > 04-Memory/idea-graph/race-test/race-nodes.jsonl
python3 tools/git-agent/freed.py check   # WARN common-field + dup-id → rc=1
```

## Артефакты

| Артефакт | SHA |
|---|---|
| `tools/git-agent/freed.py` (dotfiles) | commit `7e989090d6ec98ac0c2164db6ca71df08e2fe2cf` |
| sandbox `race-nodes.jsonl` (гонка) | sha256 `6bdfc0a6a6ef5ce32625e962ce21064e99ea7bb2d71e010ed1a7dd08f0b8ac14` |
| sandbox `_archive/race-nodes.jsonl` | sha256 `881ff88ced5644146796c584e5a168575f0870c8a5ada800723ef1017934ba01` |

**Замечание:** sandbox-артефакты после evidence удалены из дерева (чистый
прод); восстанавливаются по repro выше. Прод-сессии и `.mcode` не тронуты.