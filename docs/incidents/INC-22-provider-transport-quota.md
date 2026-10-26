# Incident record — провайдерский стол: квоты и разрывы транспорта рвут ходы

- **Incident ID:** INC-22
- **ts:** 1792837162 (2026-10-24) — первое наблюдение; подтверждён серией 2026-10-26
- **error class:** provider-quota / provider-transport (seen-before: INC-17)
- **source/tool:** провайдеры моделей (`nvidia/*`, `opencode-go/*`, `apinex/*`)
- **route_state:** open — провайдерный слой вне репо; фикс = починка квоты/ключа + резерв
- **notification_state:** владелец уведомлён (nvidia — единственная точка отказа); ИЦ/ОШ — в курсе

## Symptom
Ходы сессий падают посреди выполнения, артефакты не создаются:
- `opencode-go/*` → `Error: Go usage limit exceeded` (в т.ч. в канале писем:
  drain-инжект сразу же падал, письма возвращались в очередь).
- `nvidia/*` → `Transport: ECONNRESET` (standalone) / молчаливый hang (background);
  в моей сессии (step-5) — 3 ретрая за сутки.
- `apinex/*` → `Invalid API key` / `Missing API key` — ключ в конфиге `[redacted]`.

## Repro (дословно, эталоны воспроизведения)
1. `opencode run --agent obsidian-servant --model nvidia/z-ai/glm-5.3-flash -- "ответь
   ровно одним словом: ok"` → standalone: `Transport: ECONNRESET`; background: hang.
2. `--model opencode-go/gpt-5.6-luna` / `--model opencode-go/glm-5.3-flash` →
   `Error: Go usage limit exceeded`.
3. `--model apinex/free/claude-opus-4.6` → `Invalid API key` (позже `Missing API key`).

## Root cause (не догадка — три разных причины, разведены класс)
1. **Квота:** провайдер `opencode-go` исчерпал лимит — отдаёт отказ сразу, ход умирает.
2. **Транспорт:** провайдер `nvidia` рвёт streaming-соединение — падение на tool-ходе
   (bug #2, ОШ `ses_e8b9ae95bffeGAoRqZWtPdj2x8`), а по моей серии — и на текстовом.
3. **Отсутствующий ключ:** `apinex` в конфиге имел `[redacted]` — секрет был вымыт
   при санитайзе репозитория; провайдер не мог быть резервом.

## Fix
- Конфиг: ключи-плейсхолдеры заменены на `{env:APINEX_API_KEY}`
  (комм. `944411a`) — канон «никаких секретов в репо» + значение из окружения.
- Owner-gate: событие `apinex.secret` зарегистрировано (`fdb39d5`); форма отработала
  (accept, len 53), но **значение заредакчено слоем Code Mode** — до файла не доходит.
- Следующий шаг (не завершён): сервер ворот пишет секрет САМ (server-side),
  агент значения не видит; файл `~/.config/environment.d/apinex.conf` (600) создан пустым.
- Резерв: до починки ключа живой провайдер один (`nvidia`) — единая точка отказа.

## Evidence
- Таблица матрицы прогонов (этот файл, §Symptom) — команда + ошибка по каждому провайдеру.
- Letter ОШ 2026-10-27T00:46 (`27a8c21c5197`, ref `bugfix-runtool-transport`):
  «Классификация принята: provider-quota/transport, не тул-баг».
- Workaround (subagent-route вместо run) оформлен методом и принят УАС (комм. `3b3efcc`).
- Журнал ворот: `ask_secret apinex.secret accept secret_len=53`.

## seen-before
INC-17 (`quota-echo-tsu`) — квотный класс уже фиксировался; ссылка дана,
диагностика с нуля не повторялась. Транспортный подкласс — новый в реестре.

## Открытые хвосты
- Довести owner-gate до server-side записи секретов (директива владельца 10-27).
- Автоматизация N провайдеров: реестр «провайдер → env-переменная → файл-источник»
  + проверка полноты (директива владельца 10-27).
- Метрика «доля провалов run по провайдерам» — чтобы транспортные сбои не путались
  с правами/инструментами (оверлап с INC-20 по симптому «тула нет»).
