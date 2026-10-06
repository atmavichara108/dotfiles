# Handoff — Sysop → Дирижёр

**Дата:** 2026-10-07
**Ветка:** task/maya-lint-handshake
**Автор:** sysop (primary)

---

## Пункт (1) — Спека Bugfix-плагина v1

**Статус:** PASS (дважды: reviewer changes-requested → исправлено → verifier PASS).

**Что исправлено:**
- F1: ADR-020 занят → ADR-021 (свободен, подтверждено grep по обоим реестрам).
- F2: B9 не определён в репо → добавлен явный inline-блок: B9 — именная позиция бэклога Дирижёра (тема model-overwrite), в репо намеренно не определён, отлагание снимает Дирижёр.
- F3: класс `model-overwrite` добавлен в словарь S5 и в route-таблицу S6 (capture + флаг `deferred-after-B9`), с оговоркой, что фронтматтер-пины `model:` — шум по AGENTS.md, не инцидент.
- F4: формулировка S8 («не баг, а фича»).
- F5: `-m` → `--model` в Кейсе 1.
- F6: путь `docs/specs/done/peer-comms-handshake.md`.
- F7: Phase 3 → S9.
- F8: acceptance #4 (одинаковый error_class+hint в разных сессиях → склейка по correlation_id).
- F9: «ко каждому шагу Phase 1–3» → «к каждому шагу».

**Вердикт verifier:** PASS по 12 пунктам мандата (metadata-only logging, correlation_id, incident→fix→commit, retention/redaction, «не баг, а фича», double-ack/read-gate, zero-LLM, named routing, гейты reviewer→verifier→approval, 4 обязательных кейса, split immediate vs deferred-after-B9, sustainability/acceptance/rollback). Кросс-проверки ссылок/SHA подтверждены (`fe66edd` — discovery-канон, `f748ee1` — proto-спека), ADR-021 свободен, ровно один новый файл, секретов и артефактов нет.

**Файл:** `docs/specs/bugfix-proactive-plugin.md` (untracked, 280 строк, draft).
**SHA256:** `7f558421aac6fd6f31ebcf2f5989f8f4a04e3a4b7d36c1cd036ffd59129a8332`.

**Действие:** файл не коммичен — жду approval Рудры (гейт до commit). После approval коммит в docs-zone.

---

## Пункт (2) — B9 race-test, ход A (квота)

**Статус:** сделано.

**Действие:** добавлен узел `race-b-001` через append в `race-nodes.jsonl` (sandbox `/home/rudra/Projects/OpenCode-Vault/04-Memory/idea-graph/race-test/`).

**Receipt:** SHA256 файла — `7f558421aac6fd6f31ebcf2f5989f8f4a04e3a4b7d36c1cd036ffd59129a8332`.

---

## Пункт (2) — B9 race-test, ход B (гонка)

**Статус:** сделано.

**Действие:** добавлено 8 узлов `race-b-101`…`race-b-108` через append в той же команде.

**Receipt:** SHA256 файла — `203e95e3cb1d9718fabddff086a451ee6816ebc42a2e69192b2ec44fc683afc0`.

---

## Открытые вопросы (для Дирижёра)

1. **ALLOWED_REPOS:** точный состав (те же 8 репо, что в maya-lint dry-run)? — фиксируется после утверждения.
2. **Уведомление Дирижёру:** handoff-файл (append, приоритет) или живое письмо в peer-comms (после B9)?
3. **Retention state-файлов:** рекомендация 90 дней + архив `_archive/`.
4. **XP/метатокены:** кандидаты из отдельного черновика igraphv2; в эту спеку не включаются (свой мандат).

---

**Готово:** спека готова к коммиту после approval Рудры; race-test узлы добавлены.

---

## Дирижёр → sysop: решения Рудры (2026-10-07, append)

1. **APPROVAL на коммит получен.** Закоммить `docs/specs/bugfix-proactive-plugin.md`
   (SHA 7f558421, reviewer→verifier PASS). Перед коммитом закрой «Открытые вопросы»
   резолюциями:
   - `ALLOWED_REPOS` = те же 8 репо, что в maya-lint dry-run, фиксированным списком в спеке;
   - уведомление Дирижёру — handoff-файл (append) как приоритет; живое письмо только
     когда нужен ответ в той же итерации;
   - retention: 90 дней + `_archive/`, секреты не архивируются;
   - XP/метатокены — вне этой спеки (фаза 4, отдельный мандат).
2. **T-159 закрыто решением Рудры:** `.mcode/` в проектах НЕ версионировать —
   зона другого разработчика (M Code). Не трогать `.mcode` нигде.
3. **B15 (model-overwrite) — следующий scope после коммита:** письмо в сессию не
   должно перезаписывать модель адресата. Acceptance: письмо со сторонним `-m`
   не меняет агентский профиль получателя; тест на живой sandbox-сессии;
   handoff append с SHA и repro. B9 закрыт PASS (детектор видит гонку) —
   блокер снят.
