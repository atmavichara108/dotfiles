# Инцидент-реестр сессии TG-моста — сводка в багфикс-мастерскую

- **ts:** 2026-10-14 ( конец сессии )
- **author-session:** dotfiles-infra (sysop, primary)
- **route_state:** blocked — активной роли `bugfix` нет (`hello.sh find --role bugfix`
  → No active sessions), по BF-спеке §Шаг 3: append-only handoff вместо письма,
  silent fallback не делался.
- **notification_state:** not_required (этот handoff и есть канал)

Форма записей — `docs/incident-record-template.md` (symptom → repro → root
cause → fix/workaround → evidence → status). Секретов/текстов писем/абсолютных
путей нет.

---

## INC-A — Пермишены агента в V1-форме: `Permission denied: shell` при точных allow

- **error class:** permission-blocked
- **source/tool:** permission/agent frontmatter
- **Symptom:** fresh tg-bridge-сессия: три команды со строгим `--help`,
  явно разрешённые в `permission:`, — все три заблокированы до старта.
- **Repro:** любой агентный `.md` в map-форме пермишенов (`bash: {"…": allow}`)
  → fresh сессия → разрешённая команда → deny.
- **Root cause (подтверждён доками V2):** три дефекта вместе — (1) ключ `bash`
  вместо `shell` (V1→V2 переименование), (2) map-форма вместо массива
  `{action, resource, effect}`, (3) `external_directory` путями файлов вместо
  границы каталога `/*` (shell проверяет inferred dirs до ресурсов).
- **Fix:** `permissions:`-массив V2 в tg-bridge.md; живой preflight PASS.
- **Evidence:** repo=dotfiles — фикс в файле продукта seo-outreach
  `.opencode/agent/tg-bridge.md` (не закоммичен, под вердикт top); доки:
  opencode.ai/v2/docs/permissions, /v2/docs/agents.
- **Status:** fixed (tg-bridge); **системный хвост открыт:** ВСЕ агентные `.md`
  dotfiles (и вероятно продуктовые) в V1 map-форме — первый вызов любого
  субагента даёт тот же отказ. Нужна отдельная задача-миграция.

## INC-B — Живая отправка тестового текста в чужой топик (мой дефект исполнения)

- **error class:** tool-fail (ошибка оператора, не баг инструмента)
- **source/tool:** tool/tg-send
- **Symptom:** гейт-тест `tg-send --topic 28 "x"` без `--dry-run` ушёл живьём:
  сообщение id=83 в топике «Аутрич».
- **Repro:** tg-send принимает ЛЮБОЙ корректный `--topic` (обязателен, но не
  ограничен 33, в отличие от attach/edit/upload) + нет обязательного dry-run
  для не-владельческих топиков.
- **Root cause:** (1) моя ошибка — тест запущен без `--dry-run` в условиях
  «TG не трогать»; (2) асимметрия гейтов: у send нет owner-scope whitelist
  топиков — проектное решение, ставшее ловушкой.
- **Fix/workaround:** инцидент доложен координатору письмом (receipt
  tg-md-attach-upload); удаление id=83 — вне моего delete-whitelist {41,42},
  ждёт решения top/владельца. Кандидат-фикс (по решению top, не самовольно):
  ALLOWED_TOPICS в tg-send или обязательный --dry-run вне topic 33.
- **Evidence:** stdout прогона `ok id=83 topic=28`; письмо-отчёт с receipt.
- **Status:** reported

## INC-C — Путаница веток/адресации в командной работе (повторяющийся, замечен владельцем)

- **error class:** unknown (процессный дефект координации)
- **Symptom:** серия: «письмо отправлено, а его не видно», «работа идёт не в
  той ветке», «пустая ветка уже создана — работай в ней» (её нет).
- **Repro (свежий кейс):** координатор объявил ветку `task/tg-md-attach-…`
  «уже созданной» — в репо её не было (была `task/tg-upload` без кода);
  параллельно код задачи оседал в worktree чужой ветки и в stash^3 (untracked),
  откуда его поднимал другой исполнитель.
- **Root cause:** между ролями нет единого источника истины по ветке/адресату:
  (1) сообщения ссылаются на ветки/файлы, не проверенные отправителем в git;
  (2) untracked-файлы уезжают в stash tree-cop'ом и теряются из виду; (3)
  peer-comms receipts пишутся ДО подтверждения доставки (post-verified sent не
  реализован — зафиксировано ранее в 2026-10-14-soft-delivery-receipt-started),
  отправитель считает письмо доставленным, адресат — не получал.
- **Fix/workaround:** [гипотеза→задача] задача-контракт «назови ветку — проверь
  git» (отправитель прикладывает `git rev-parse` sha ссылки); задача на
  post-verified `sent` в letter.sh (уже заявлялась); interim: в каждом письме
  указывать branch@shafacta, получателю — сверять.
- **Evidence:** git branch --list (ветки нет), stash@{0}^3 (код там),
  receipts-out.jsonl (sent без started-подтверждений), handoff
  2026-10-14-soft-delivery-receipt-started.md.
- **Status:** open → прошу мастерскую завести ID (класс: process/coordination)

## INC-D — Transport-обрыв peer-comms после отправки (ложный сигнал ошибки)

- **error class:** provider-timeout (транспорт сокета)
- **source/tool:** tool/letter.sh (socket close)
- **Symptom:** `letter.sh` в фоне: «socket connection was closed unexpectedly»,
  rc=1; по факту письмо доставлено — журнал содержит `sent`.
- **Repro:** длинное письмо через letter.sh на сессию-адресата, обрыв
  пост-верификационного шага.
- **Root cause:** джурнал `sent` пишется до блокирующего вызова (известный gap);
  обрыв в post-send проверке даёт rc=1 при успешной отправке → риск no-resend
  конфликта/дубля при ретраях.
- **Fix/workaround:** сверяться по receipts-out.jsonl перед ретраем (сделано);
  полноценный post-verified sent — та же задача, что в INC-C.
- **Evidence:** shell-id прогона rc=1 + журнал `sent tg-go-send`.
- **Status:** reported (workaround штатный)

## INC-E — Маршрут багфикс-мастерской: активная роль отсутствует

- **error class:** permission-blocked (route-level)
- **Symptom:** `hello.sh find --role bugfix` → no active sessions.
- **Root cause:** роль bugfix не запущена ни в одном проекте; BF-спека
  предусматривает: blocked + append-only handoff (сделано этим файлом),
  silent fallback запрещён.
- **Status:** reported —просьба к владельцу/топу поднять активную роль bugfix.

## Побочные наблюдения (не инциденты, фиксация)

- `LAST_LOGIN_v2` (подчёркивание) не ловится префиксом «Last Login» — вопрос
  координатору задан, решение за ним.
- tg-edit `{"id": null}` уходил литералом «None» — исправлено (7cdde9f,
  verifier-замечание закрыто).
- Флаги без значения в tg-edit дают IndexError-трейсбек (fail-closed rc=1,
  cosmetique) — не блокер.
- Capture-журнал dotfiles за день: 24 записи (quota 6, timeout 3, tool-fail 12,
  unknown 3) — паттерн quota/timeout на совести провайдеров, ретраи штатные.
