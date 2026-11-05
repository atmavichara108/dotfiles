---
description: "Сводный доклад ИЦ владельцу: живые линии, что ждёт его слова, блокеры, закрыто с evidence"
agent: master-enginer
---
Команда: /report $ARGUMENTS

Без аргумента — все линии.

## Жёсткие правила
- **Слово владельца — единственная авторизация;** `basis: quoted`, домыслы
  запрещены; неоднозначность → вопрос, не трактовка.
- **`general` не является silent fallback;** неизвестный маршрут = `UNROUTABLE`.
- Ссылки: `AGENTS.md`, `.opencode/memory/decisions.md`, `docs/decisions.md`,
  `docs/incidents/`, `docs/handoffs/`, `tools/ship-mail/README.md`,
  `.opencode/memory/session-reports/`.
- Доклад — человеческим языком: без кода, без диффов, без пересказа одних и
  тех же файлов; объём — один экран.

## Шаги

1. **Источники:**
   - ship-mail: `bash tools/ship-mail/ship-mail.sh inbox <sessionID>` (первым
     шагом), `python3 tools/ship-mail/waits.py list`;
   - `.opencode/memory/inbox.md`, `.opencode/memory/decisions.md`,
     `.opencode/memory/session-reports/`;
   - `docs/handoffs/`, `docs/incidents/`, `docs/techdebt.md`, `docs/roadmap.md`;
   - git: `git branch --show-current`, `git log --oneline --decorate -20`,
     `git status --short`;
   - `tools/owner-gate/events.json` — если есть открытые заявки на события.

2. **Группировка:**
   - (а) работает сейчас;
   - (б) ждёт слова владельца — каждой строкой прямой вопрос;
   - (в) блокеры/инциденты;
   - (г) закрыто с evidence за период (путь/коммит/вердикт/письмо, не «сделано»).

3. **Reader-aware (Р-092/Р-093):**
   - `waits.py overdue` показывает только form-declared просрочки; answered/stitch
     идут отдельной строкой «ОТВЕТ БЕЗ ПРИШИВКИ (lag N)», не в ПРОСРОЧЕНО;
   - `waits.py stitch-report` и `follower.py --json-line` используются для
     меток N/M/K/X, no-meta («МЕТКИ НЕТ — ждёт разметки») и stale-meta;
   - sweep-lag > 60м = дефект детектора, не «пинок человеку»;
   - если `ready=false` — класс ЗАСТОЙ, не «готово».

3. **Простой человеческий язык:** без кода, без диффов, без пересказа одних
   и тех же файлов; объём — один экран.

4. **Не принимать решений за владельца.** Спорное — вопрос с вариантами,
   без выбранной «по умолчанию» трактовки.

5. **Дайджест дописать** в `.opencode/memory/session-reports/<YYYY-MM-DD>-report.md`
   (append-only, без правки прошлых записей).

## Выход
Доклад по группам (а)–(г) + путь записи в session-reports.
