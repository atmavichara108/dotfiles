---
kind: task
status: proposed
executor: sysop
owner: Max Rudra
date: 2026-10-10
title: seo-outreach — bootstrap локального агентного runtime overlay (один primary top)
spec-home: /home/rudra/dotfiles/docs/specs/
selector: seo-outreach-agent-runtime-bootstrap
related:
  - ssa-control-agent-harness-bootstrap.md
  - /home/rudra/Projects/SSA/products/seo-outreach/AGENTS.md
  - /home/rudra/Projects/SSA/products/seo-outreach/docs/architecture.md
  - /home/rudra/Projects/SSA/products/seo-outreach/docs/decisions.md
  - /home/rudra/Projects/SSA/products/seo-outreach/docs/specs/seo-outreach-mvp-v0.1.md
tags: [spec, ssa, seo-outreach, product, overlay, opencode, agents, bootstrap]
---

# seo-outreach — bootstrap локального агентного runtime overlay

> **Статус: `proposed`, НЕ approved.** Документ ничего не разворачивает, не
> настраивает провайдеров, не отправляет писем и не даёт разрешения на реализацию
> продукта. Он описывает установку локального агентного overlay для продуктового
> репо ПОСЛЕ явного approval пользователя. До approval — только чтение/обсуждение.
> Эта задача — только подготовка спеки.

> **Парная спека:** [`ssa-control-agent-harness-bootstrap.md`](./ssa-control-agent-harness-bootstrap.md).
> Этот overlay ОБЯЗАН быть совместим с control-спекой: единый primary `top`,
> граница control↔product, global-vs-local hooks, модель доступа.

---

## 0. Классы решений

- **[confirmed]** — подтверждено пользователем (цитаты/производные в
  `SSA/products/seo-outreach/docs/decisions.md`).
- **[derived]** — инженерное предложение из confirmed + правил экосистемы.
- **[open]** — нерешённый вопрос / decision gate.

`[derived]`/`[open]` нельзя выдавать за `[confirmed]`.

---

## 1. Предпосылки

1. **[confirmed]** `products/seo-outreach/` — отдельный git-репо; `~/Projects/SSA/`
   не git; SERPlux и `seo_project_pack*` — вне (референс/архив, не переносить).
2. Сейчас в репо есть только документные артефакты (`AGENTS.md`, `README.md`,
   `docs/architecture.md`, `docs/decisions.md`,
   `docs/bootstrap/implementation-approval-brief.md`,
   `docs/specs/seo-outreach-mvp-v0.1.md`). Директории `.opencode/` **нет**.
3. **[confirmed]** `top` упомянут в `AGENTS.md`, но runtime `top` сейчас НЕ
   существует: текст в `AGENTS.md` не делает его обнаруживаемым runtime-ом.
4. **[confirmed]** При открытии этого репо в OpenCode агентский слой (`top`,
   скилы, команды, права, hooks) должен РЕАЛЬНО работать, не только быть описан.
5. **[confirmed]** Один primary `top`; НЕ создавать второй primary, не
   инстанцировать флот субагентов без измеренной нужды.
6. **[confirmed]** Полный SEO-аутрич-конвейер, 2 фазы: фаза 1 под контролем
   человека; фаза 2 автоматизирует сбор/обработку, НО каждое внешнее письмо
   требует отдельного ручного approval; переговоры/условия/деньги — всегда
   human-owned. Автофаза approval НЕ отменяет.
7. **[confirmed]** Стек старта: Sheets/SQLite. Web/Postgres/queues — только
   будущий migration seam, не сейчас. Инстансы/данные клиентов изолированы.
8. Исполнитель — `sysop` (dotfiles local primary). Код приложения (`*.py`, `*.gs`,
   prod-конфиги) этой спекой НЕ создаётся и НЕ трогается.

---

## 2. Цель

Установить в `products/seo-outreach/` минимальный локальный overlay, который при
открытии репо-корня в OpenCode даёт реально работающий primary `top`, минимальные
локальные скилы/команды/hooks под полный аутрич-конвейер, детерминированные
side-effect гейты, SSOT доков/памяти продукта и локальные гейты
безопасности/приёмки. Overlay совместим с control-спекой и не дублирует общие
определения без версионированного источника/синка.

Anti-goals: второй primary; дубли общих определений без синка; флот субагентов без
измеренной нужды; любой код приложения; любая настройка провайдера/отправка/деплой;
касание реального SMTP/IMAP; игровая терминология/Maya.

---

## 3. Единый `top` в продуктовом корне

### 3.1. Правило
- **[confirmed]** Один primary `top` доступен при открытии этого репо. НЕ создавать
  второй primary и НЕ дублировать общие определения без версионированного
  источника/синка.
- Способ загрузки берётся из решения control-спеки (§3 той спеки). Если выбран
  вариант с дублированием (project-local копия/symlint), локальная копия
  `products/seo-outreach/.opencode/agent/top.md` несёт `source:` и
  `schema-version:` и покрывается тем же `top-sync-check`.
- Авто-подхват соседнего `.opencode/` недопустим как единственный механизм:
  открытие именно этого корня должно давать `top` без ручной настройки окружения.

### 3.2. Decision gate
- Если единый `top` нельзя загрузить в этом корне без дублирования и без решения
  control-спеки — остановиться и сослаться на decision gate control-спеки
  (`0002-top-loading.md`), не плодить primary молча.

---

## 4. Операционная модель overlay (не просто список файлов)

### 4.1. Топология агентов
- **`top`** — единственный primary продукта: ведёт продукт в границах (контракты
  модулей, версии схем, тесты, журналирование/аудит, доки/changelog, правила
  `top`, dry-run по умолчанию, детерминированные safety-гейты).
- Субагентов на bootstrap НЕ создавать. Кандидатные способности из `AGENTS.md`
  (discovery, scoring, contacts, outreach, parsing, reviewer) — **[open]** список,
  не runtime; каждая — отдельным подтверждением scope по измеренной нужде.
- Глобальные reviewer/verifier/researcher — не копировать; вызываются как есть
  (если доступны), остаются в global/dotfiles-владении.

### 4.2. Локальные скилы (минимум, под полный конвейер) **[derived]**
Скилы — только оркестровка/подготовка материала; LLM-рассуждение отделено от
детерминированных side-effect гейтов (§4.4). Side-effects на bootstrap = нет.

| Скил | Назначение (конвейер) | Side-effects на bootstrap |
|---|---|---|
| `campaign` | параметры/создание кампании (конфиг) | нет (dry-run; запись только локальных конфигов продукта вне git-секретов) |
| `discovery` | поиск площадок по источникам | нет (на bootstrap не выполняется; контракт/схема только) |
| `scoring` | dedup/filters/scoring | нет |
| `contacts` | сбор/верификация контактов и условий | нет |
| `pre-send-gate` | детерминированный pre-send approval gate | нет; на bootstrap только контракт гейта, не отправка |
| `inbox` | разбор входящих/классификация/извлечение | нет |
| `handoff` | human handoff карточек | нет |
| `export` | export/package | нет |
| `monitor` | monitoring/incident stop (Emergency Stop) | нет |

### 4.3. Локальные команды (минимум) **[derived]**
| Команда | Что делает |
|---|---|
| `/campaign` | показать/подготовить параметры кампании (dry-run) |
| `/dryrun` | прогнать конвейер в dry-run без side-effects |
| `/status` | статус продукта: задачи/роадмап/проблемы/техдолг |
| `/stop` | показать/проверить Emergency Stop контракт (без исполнения на bootstrap) |

### 4.4. Детерминированные side-effect гейты
- **[confirmed/derived]** Любой side-effect (отправка, запись, платный запрос)
  проходит через детерминированный код, отделённый от LLM-рассуждения. LLM
  готовит/извлекает, но НЕ отправляет, НЕ обещает, НЕ принимает обязательств.
- Pre-send gate — детерминированный, в текущем bootstrap существует только как
  контракт/схема (без реальной отправки). `human_owned` делает автоотправку
  технически невозможной. Emergency Stop и глобальный suppression list — контракт.
- `dry_run` по умолчанию во всех контрактах модулей.

### 4.5. Доки / память продукта (SSOT)
- SSOT продукта: `docs/decisions.md`, `docs/architecture.md`, плюс заводятся
  минимальные `docs/roadmap.md`, `docs/tasks.md`, `docs/problems.md`,
  `docs/techdebt.md`, `docs/runbook.md`, `docs/module-catalog.md`.
- Точное владение относительно control **[confirmed]**: продукт владеет своим
  кодом, спеками, данными; control владеет портфелем/ADR/модульным реестром.
  Общие определения не дублируются без версионированного источника/синка.

### 4.6. Hooks: global-vs-local
- **[confirmed]** Глобальные hooks НЕ менять; общие остаются во владении dotfiles.
  SSA/продукт-специфика — только локально в `products/seo-outreach/.opencode/`.
- Локальные hooks продукта (если нужны) — детерминированные, без секретов, без
  реальных сетевых эффектов; задокументированы в `docs/hooks-map.md`.

### 4.7. Модель доступа и красные линии **[confirmed/derived]**
- `top` пишет только внутри `products/seo-outreach/`.
- **Секреты и клиентские БД — не в git** (`.gitignore` уже есть; overlay не
  добавляет секретов).
- **Verifier scope** — read-only; точный контракт evidence (точные пути, DoD,
  exclusions); **deny на секреты/ПД сохраняется**. Live-read verifier **[open]**.
- Изолированный per-client runtime/данные **[confirmed]**: нет общего
  tenant-runtime, нет общей фабрики между клиентами.

---

## 5. Стадии исполнения (упорядочено; после approval)

> Выполняет `sysop` в `task/*`-ветке репо продукта. Коммит/push/destructive git —
> только после отдельного explicit approval. Force push запрещён навсегда. Код
> приложения не создаётся.

### 5.1. Стадия 0 — предпроверка
- Прочитать актуальные `AGENTS.md`, `architecture.md`, `decisions.md`,
  `implementation-approval-brief.md`, `seo-outreach-mvp-v0.1.md`, парную
  control-спеку и её решение по загрузке `top`.
- Зафиксировать отсутствие `.opencode/`; завести `task/*`-ветку.

### 5.2. Стадия 1 — загрузка `top`
- Применить стратегию из control-спеки. При дублировании — локальная копия
  `top.md` с `source:`/`schema-version:` + покрытие `top-sync-check`.
- Если без решения control-спеки единый `top` не грузится — остановиться на
  decision gate (§3.2).

### 5.3. Стадия 2 — overlay-скилы/команды/hooks
- Создать `products/seo-outreach/.opencode/agent/top.md` (frontmatter
  `mode: primary`, модель `[open]`/по правилу, permission с deny на секреты/ПД и
  destructive, `dry_run`-ориентация).
- Создать локальные скилы §4.2 и команды §4.3 (только контракты/оркестровка,
  side-effects выключены).
- Создать локальные hooks только при реальной нужде; задокументировать.

### 5.4. Стадия 3 — доки/память продукта
- Завести минимальные `roadmap.md`, `tasks.md`, `problems.md`, `techdebt.md`,
  `runbook.md`, `module-catalog.md`, `hooks-map.md`.

### 5.5. Стадия 4 — безопасность/приёмка (локально)
- Зафиксировать контракты гейтов §4.4 и §6 как проверяемые инварианты (без
  исполнения отправки).
- Создать `docs/acceptance/` с чек-листом §7 и шаблоном evidence (без секретов/ПД).

### 5.6. Стадия 5 — gates
- Финальный staged tree → узкие детерминированные/статические checks → SHA-256
  staged diff → reviewer → verifier (оба по одному hash). Любая правка аннулирует
  вердикты. Коммит/tag/перенос — после verifier PASS и explicit approval.

---

## 6. Локальная безопасность / приёмка (жёсткие инварианты) **[confirmed]**

- Тест/dry-run **НИКОГДА** не касается реального SMTP/IMAP, НЕ шлёт писем даже в
  тестовый ящик, без платных/внешних эффектов.
- Живой пилот — только позже и только после: закрытия открытых Q01–Q28; правовых/
  AUP/провайдер/владелец/безопасность-гейтов; и отдельного approval на КАЖДОЕ
  письмо. Никакой настройки провайдера/отправки/деплоя на bootstrap.
- Опасные сценарии — нулевая терпимость: письмо после отказа, дубли, обход
  human handoff, утечка секрета.

---

## 7. Acceptance (критерии приёмки)

### 7.1. Живой smoke открытием ОБОИХ корней **[обязательно, confirmed]**
Приёмка выполняется ОТКРЫТИЕМ OpenCode отдельно в обоих корнях (`control/` и этом
продукте), доказывая реальное поведение агента/скилов/команд/прав/hooks. Одной
инспекции конфигов недостаточно. Для продукта:
1. `top` обнаруживается и является единственным primary (не текст в `AGENTS.md`).
2. Локальные скилы/команды видны и вызываемы в dry-run.
3. Side-effect гейты присутствуют как детерминированные контракты; реальная
   отправка технически недоступна.
4. При дублировании `top` — `top-sync-check` зелёный.

Затем reviewer → verifier.

### 7.2. Verifier
- **[confirmed]** read-only; БЕЗ секретов/ПД; точный evidence-контракт (пути, DoD,
  exclusions); deny на секреты/ПД сохраняется.
- **[open]** Текущий live-read verifier НЕ подтверждён — нерешённый gate; приёмка
  не полна, пока он не подтверждён вживую. Явно отметить в evidence.

### 7.3. Runtime-факт
- Явно зафиксировать: до исполнения этой спеки runtime `top` НЕ существует; текст
  в `AGENTS.md` сам по себе не делает его обнаруживаемым.

---

## 8. Границы и out-of-scope

- **НЕ** писать код приложения (`*.py`, `*.gs`, prod-конфиги) — зона project
  build-агентов.
- **НЕ** настраивать провайдеров/отправку/деплой; **НЕ** касаться SMTP/IMAP.
- **НЕ** создавать второй primary; **НЕ** инстанцировать субагентов без измеренной
  нужды.
- **НЕ** дублировать общие определения без версионированного источника/синка.
- **НЕ** менять глобальные/общие hooks (только локальные SSA).
- **НЕ** вводить web/Postgres/queues (только будущий migration seam).
- **НЕ** вводить игровую терминологию/Maya.

---

## 9. Rollback

- Overlay — новые файлы в `products/seo-outreach/.opencode/` и `docs/`. Rollback =
  удалить добавленные пути в `task/*`-ветке (reverse точного списка) либо не
  мёржить ветку.
- Глобальные/общие hooks не трогаются — системного отката не требуется.

---

## 10. Зависимости / блокеры

- **D1 (блокер реализации продукта, не bootstrap overlay):** текущий
  `docs/specs/seo-outreach-mvp-v0.1.md` всё ещё исключает реальную отправку. Его
  нужно ОТДЕЛЬНОЙ правкой привести к controlled real-email pilot (gated) ДО
  реализации продукта. Указывается как dependency; **сам product-спек в этой
  задаче НЕ менять**.
- **D2:** решение control-спеки по загрузке `top` (§3) — предпосылка для §5.2.
- **D3:** открытые Q01–Q28, правовые/AUP/провайдер/владелец/безопасность-гейты —
  предпосылки живого пилота, не bootstrap.

---

## 11. Approval-гейты

1. Approval на исполнение overlay целиком (перевод из `proposed`).
2. Отдельный approval на любой commit/push/tag/перенос в `done/`.
3. Отдельный approval на каждую будущую capability-субагента (по измеренной нужде).
4. Расширение scope — новый proposal; прежнее согласие не переносится.

---

## 12. Открытые вопросы (сводка `[open]`)

- O1. Способ загрузки `top` (из control decision gate).
- O2. Модель `top` (ярус/ID).
- O3. Live-read verifier — не подтверждён.
- O4. Лицензия НЕ выбрана; различать права на код/модули, данные клиента,
  настроенную БД, развёртывание, модификации.
- O5. Состав будущих субагентов — кандидаты, не runtime.
- O6. Q01–Q28, провайдеры/тарифы, числовые пороги, правовая проверка — не закрыты.

---

## 13. Связи

- Парная control-спека: [`ssa-control-agent-harness-bootstrap.md`](./ssa-control-agent-harness-bootstrap.md)
  (единый `top`, границы control↔product, global-vs-local hooks, модель доступа).
- Архитектура/решения продукта: `architecture.md`, `decisions.md`,
  `implementation-approval-brief.md`.
- Канонический product-спек (не менять в этой задаче): `seo-outreach-mvp-v0.1.md`.
