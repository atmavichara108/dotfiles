---
type: Execution Spec
title: New API provider onboarding (M Code + OpenCode)
project: dotfiles
kind: task
status: ready
spec-home: /home/rudra/dotfiles/docs/specs
timestamp: 2026-10-09
---

# New API provider onboarding (M Code + OpenCode)

## Goal

Провайдер `newapi` (локальный шлюз New API на http://localhost:3000/v1)
должен появиться в конфигах И M Code, И OpenCode v2, чтобы агенты могли
садиться на алиасы `free-code` / `free-general` / `free-vision` на время
сессии, а шлюз сам делал failover между бесплатными каналами.

Ключ API (`newapi` -> auth.json) уже заведён, вводить его не нужно.

## Current state (проверено 2026-10-09)

1. `dotfiles/opencode-global/.config/opencode/mcode.jsonc` (он же
   `~/.config/mcode/mcode.jsonc`, симлинк): блок `provider.newapi` ЕСТЬ,
   но конфиг НЕ парсится — после закрывающей `}` блока newapi (строка 11)
   пропущена запятая перед `"linaliapi"`. Поэтому M Code не видит модели.
2. `dotfiles/opencode-global/.config/opencode/opencode.jsonc`: блока
   `newapi` НЕТ вообще (проверено grep — 0 совпадений).
3. Шлюз живой: `systemctl --user status new-api`; `/v1/models` отдаёт 3
   алиаса; все три алиаса отвечают HTTP 200 на тестовый chat/completions.

## Steps

### Шаг 1 — починить mcode.jsonc

Файл: `dotfiles/opencode-global/.config/opencode/mcode.jsonc`

Заменить строки 10-12:

```json
    "models": ["free-code", "free-general", "free-vision"]
  }
    "linaliapi": {
```

на:

```json
    "models": ["free-code", "free-general", "free-vision"]
  },
    "linaliapi": {
```

Блок newapi должен остаться в форме:

```json
  "newapi": {
    "npm": "@ai-sdk/openai-compatible",
    "name": "New API Gateway",
    "options": {
      "baseURL": "http://localhost:3000/v1"
    },
    "models": ["free-code", "free-general", "free-vision"]
  }
```

### Шаг 2 — добавить newapi в opencode.jsonc

Файл: `dotfiles/opencode-global/.config/opencode/opencode.jsonc`

Внутрь блока `"providers": { ... }` (рядом с `"amd-radeon"`) вставить:

```json
    "newapi": {
      "package": "aisdk:@ai-sdk/openai-compatible",
      "settings": {
        "baseURL": "http://localhost:3000/v1"
      },
      "models": {
        "free-code": { "name": "Free Code (gateway)", "tool_call": true, "temperature": true },
        "free-general": { "name": "Free General (gateway)", "tool_call": true, "temperature": true },
        "free-vision": { "name": "Free Vision (gateway)", "tool_call": true, "attachment": true, "temperature": true }
      }
    },
```

Формат v2: `package: aisdk:...` + `settings` (НЕ npm/options — это форма v1).
Список `models` — объект с описаниями, не массив строк.

### Шаг 3 — проверить ключ

`~/.local/share/opencode/auth.json` должен содержать id `newapi`.
Если нет — это не твоя зона: сообщить, что нужен ключ, не выдумывать его.

## Verification (все обязательны)

1. Оба файла парсятся как JSONC (нет ошибки "Expecting ',' delimiter").
2. `python3 -c "import json,re; ..."` или jq: в mcode.jsonc провайдер
   `newapi` присутствует, в opencode.jsonc `providers.newapi` присутствует.
3. Секретов в конфигах нет: `grep -i "sk-" mcode.jsonc opencode.jsonc` —
   только baseURL, никаких ключей (ключ живёт в auth.json).
4. `systemctl --user is-active new-api` -> `active`.
5. `curl -s http://localhost:3000/v1/models -H "Authorization: Bearer
   $(cat /tmp/.na_tk)"` отдаёт `free-code`, `free-general`, `free-vision`.
6. Каждый алиас отвечает 200 на `POST /v1/chat/completions` с prompt
   "Reply with exactly: OK", max_tokens 20.

## After

Сказать пользователю: перезапустить M Code и OpenCode (конфиг читается
один раз при старте). В списке моделей появится `newapi/free-code` и т.д.

## Red lines

- Не трогать остальные провайдеры и агент-блоки в обоих конфигах.
- API-ключи не вставлять в конфиги вообще (только auth.json).
- Никаких правок конфигов M Code кроме описанной запятой.

## Done when

Оба конфига парсятся, провайдер newapi виден в обоих, шлюз active,
пользователь подтвердил появление моделей после перезапуска.
