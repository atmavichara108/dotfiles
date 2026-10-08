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
