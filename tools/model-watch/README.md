# model-watch

Zero-LLM монитор списков моделей провайдеров. Тянет апстрим-каталог
https://models.dev/api.json (226 провайдеров), сверяет с provider-блоком
`opencode-global/.config/opencode/opencode.jsonc` и встроенными провайдерами
`opencode` / `opencode-go`, пишет снапшот
`~/Projects/OpenCode-Vault/control-plane/model-catalog.json`
(формат: `{generated_at, providers:{id:{models:{id:{in,cost_in,cost_out,free}}}}}`)
и печатает дельту к предыдущему снапшоту.

## Запуск вручную

    python3 tools/model-watch/model-watch.py            # сеть + запись снапшота
    python3 tools/model-watch/model-watch.py --offline api.json

## Дельта

Печатается после строки `delta к предыдущему снапшоту: N изменений`:
`+` прибыло модели, `-` убыло, `~ ... стало бесплатным` / `~ ... цена ...` /
`~ ... в каталоге:` — изменения статуса и цен. Первый запуск: N = всё, что
есть (сравнение с пустым снапшотом).

## Активация таймера (отдельный шаг, вручную)

Unit-файлы в этом каталоге, активация не выполнена. Включить:

    cp tools/model-watch/model-watch.{service,timer} ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable --now model-watch.timer   # перезапуск каждые 24h
    systemctl --user list-timers 'model-watch*'

Выключить: `systemctl --user disable --now model-watch.timer`.

## Гейт свежести

    python3 tools/model-watch/gate-check.py   # exit 1: снапшота нет или >7 дней

Обход: `MODEL_OK=1 ...`. Хук в волт подключается отдельным шагом (не здесь).

## Связь с T-177 (фаза 5)

Снапшот — источник кандидатов 3 классификаторов на бесплатных моделях к
фазе 5: `jev-1.13-free`, `ling-3.1-flash-free`, `nemotron-3.5-lightning-free`.
jev-моделей в models.dev нет — они включены Рудрой в консоли opencode.ai
(org SERP, платный jev-1.13 $0.04/$0.00); в снапшоте они значатся `in:false`
из декларации конфига — ждут propagated каталога Zen.

## Статус Jev (2026-10-08, проверка на живом окружении)

jev-1.13 и jev-1.13-free есть в первоисточнике models.dev и в снапшоте,
включены в консоли SERP, но локальный кэш моделей (`~/.cache/opencode/models.json`,
от 2026-09-27) их не содержит; `opencode models` кэш не обновляет.
Декларация в opencode.jsonc оставлена. Смоук `opencode run -m opencode-go/jev-1.13-free`
даёт `Model unavailable` до обновления кэша (перезапуск сервера OpenCode).

## Проверка пинов агентов (pin-check)

Пин модели, которой нет в каталоге, OpenCode принимает БЕЗ ошибки
(`POST /api/session/<id>/model` → 204) и на запросе тихо уводит сессию на
дефолтную модель агента (инцидент 2026-11-19: verifier
`nvidia/moonshotai/kimi-k2.6` → AMD-ключ с лимитом 1 запрос/сутки).

    python3 tools/model-watch/pin-check.py                 # оба слоя dotfiles
    python3 tools/model-watch/pin-check.py --staged         # то, что в коммите
    python3 tools/model-watch/pin-check.py --strict         # любой битый пин = FAIL
    python3 tools/model-watch/pin-check.py --offline        # models.dev (advisory)
    python3 tools/model-watch/pin-check.py --no-provider-check   # только каталог OpenCode
    python3 tools/model-watch/pin-check-selftest.py         # selftest (зелёный прогон)

Каталог — только `GET /api/model` живой машины (канон метода): у
openai-compatible провайдеров `/api/provider` пуст и это НЕ значит «моделей нет».
Токен — `~/.config/opencode/service.json` (тот же путь, что у `wake.py`).

## Два источника живости пина (с 20.11, инцидент BF-20261120-01)

Каталога OpenCode мало: у openai-compatible провайдеров он статический, и
умершие модели в нём остаются (24 агента стояли на
`nvidia/deepseek-ai/deepseek-v4.1-flash`: в каталоге есть, у провайдера —
`410 Gone`, EOL 2026-11-16). Поэтому:

1. **Источник 1 — каталог OpenCode** (`GET /api/model`): «пин разрешается в
   контуре».
2. **Источник 2 — список моделей провайдера на НАШЕМ ключе**
   (`GET {endpoint}/models`): «модель реально обслуживается тем ключом, которым
   мы платим». Эндпоинты и id провайдеров — из каталога ротатора
   (`~/Projects/OpenCode-Vault/tools/key-rotator/providers.json`); ключ берётся
   в порядке: env → vault `.env` → credential-store OpenCode (`auth.json`, затем
   `opencode.db`/таблица `credential`). Ключи в отчёт не попадают.

Пин жив, только если он есть в обоих источниках. Источник 2 недоступен (нет
ключа, провайдер не отдаёт список, `403`) → **WARN, не FAIL**: гейт не должен
вставать из-за провайдера, который нечем проверить; молчаливый PASS без
предупреждения — тот же дефект.

**Алиасы шлюза** (`newapi/free-code`, `newapi/free-general`) — особый случай:
их провайдер сам шлюз. Живость алиаса = алиас есть в каталоге шлюза
(`GET {gateway}/v1/models`) **И** проходит живую чат-пробу (с tools; ответ
`404/410` = провайдер не отдаёт → FAIL, «не удалось проверить» → WARN).
Кэш живой пробы: успех — 15 минут (гейт не тормозит каждый коммит), отказ
провайдера (`404/410`) — 1 минута, чтобы починка провайдера была видна сразу
(кэш не должен прятать отказ дольше, чем нужно). Кэш — в
`~/.local/state/opencode/model-watch/pin-cache.json`, обход — `--no-alias-cache`.
Пустой ответ провайдера (список моделей пуст) трактуется как «нечем проверить»:
WARN, не FAIL — молчаливый FAIL на весь флот провайдера был бы тем же дефектом,
что и пустой каталог OpenCode.

**Факт по Р-109 (предупреждение, не блокировка):** если модель проверяющего
входит в каналы алиаса (БД шлюза `~/.local/share/newapi/one-api.db`, таблица
`channels.model_mapping`), печатается строка с id канала. На 20.11 это
вскрыто: каналы 30 и 33 — `poolside/laguna-xs-2.1` (модель reviewer'а), канал
39 — `recursive/flint-v1.0` (модель verifier'а).

Вердикты: `MISSING_MODEL`, `MISSING_PROVIDER`, `MISSING_AT_PROVIDER`,
`MALFORMED` — блокируют; `UNPROBEABLE`, `ALIAS_NOT_PROBED` — предупреждения.
Спека: `docs/specs/pin-guard.md` (§4.1, §4.4, §5).

Diff-гейт: в режиме `--staged` блокируется только НОВЫЙ битый пин (не битый в
HEAD). Уже сломанный пин печатается как ⚠️, но не блокирует чужие коммиты —
иначе один старый пин встанет весь флот. `--strict` отключает это правило.

Отчёт (меты-only, без секретов): `~/.local/state/opencode/model-watch/pin-report.json`.

Обход (осознанный): `PIN_OK=1` — причина обязательна в сообщении коммита.
