---
type: Spec
title: M Code + OpenCode — единый SSOT провайдеров (dotfiles)
description: Execution spec для dotfiles-агента (sysop): починка SSOT-рассинхрона провайдеров между M Code (Desktop) и OpenCode TUI. Создать mcode.jsonc в dotfiles (8 провайдеров), добавить local-deepseek + modelhub в opencode.jsonc, выровнять providers.amd-radeon до 7 моделей. Scope — только dotfiles конфиги.
tags: [spec, dotfiles, mcode, opencode, provider, ssot, dual-sdk]
timestamp: 2026-10-01
status: draft
---

# Spec: M Code + OpenCode — единый SSOT провайдеров (dotfiles)

> Владелец исполнения — **dotfiles project agents / sysop**, не librarian и не
> M Code-агент. Только правки конфигов dotfiles; ключи не трогать (secret-service
> M Code и auth.json OpenCode — отдельные, вне этого спека).

## 1. Intent

Сделать dotfiles единым источником правды (SSOT) по кастомным провайдерам для
**обоих** SDK — M Code (Desktop, форк OpenCode) и OpenCode TUI. Сейчас M Code
читает свой локальный `mcode.jsonc` (8 провайдеров), а dotfiles `opencode.jsonc`
(6) → рассинхрон: `local-deepseek` и `modelhub` пропали из M Code после
перезапуска.

## 2. Контекст / почему

- **Корень:** M Code ищет конфиг `mcode.json(c)`, dotfiles содержит только
  `opencode.json(c)` (upstream-имя, M Code его игнорирует). Поэтому M Code не
  видит провайдеры dotfiles и берёт свой локальный `mcode.jsonc`.
- **Диагноз согласован с OpenCode-сессией** (2026-10-01): единого дефекта нет,
  каждый провайдер падает по-своему (apinex 402 платный, justwoker 403 BLOCKED,
  nvidia 401 нет ключа, amd-radeon таймаут). Отдельный SSOT конфига — это
  **не** лечит падения по ключам (ключи в secret-service vs auth.json/.env),
  но восстанавливает видимость провайдеров и единообразие конфига.
- Подробности архитектуры: `/home/rudra/Projects/OpenCode-Vault/06-Audits/2026-10-01-dual-sdk-architecture.md`.

## 3. Scope

**In (dotfiles only):**
- `/home/rudra/dotfiles/opencode-global/.config/opencode/mcode.jsonc` — **создать**.
- `/home/rudra/dotfiles/opencode-global/.config/opencode/opencode.jsonc` — править
  блоки `provider` (v1) и `providers` (v2).

**Out (НЕ трогать):**
- Локальный `/home/rudra/.local/share/m-code-data/config/mcode.jsonc` — это
  зона M Code/владельца, не dotfiles.
- Ключи провайдеров (secret-service M Code, `auth.json` OpenCode, vault `.env`).
- Код приложений.

## 4. Изменения

### 4.1. Создать `mcode.jsonc` в dotfiles (единый SSOT, 8 провайдеров)

Путь: `/home/rudra/dotfiles/opencode-global/.config/opencode/mcode.jsonc`.

Взять **полное содержимое** текущего `/home/rudra/.local/share/m-code-data/config/mcode.jsonc`
(281 строка, 8 провайдеров: linaliapi, amd-radeon [7 моделей], anymodel, apinex,
justwoker, local-deepseek, modelhub, vercel) **без изменений** — оно уже содержит
все 8 кастомных провайдеров полными v1-блоками (`npm`/`options`/`models`).

Сохранить `$schema` без изменений (ведёт на M-Code-репозиторий).

### 4.2. Добавить `local-deepseek` + `modelhub` в `opencode.jsonc`

В оба блока — `provider` (v1) и `providers` (v2).

**`provider` (v1):**
```jsonc
"local-deepseek": {
  "npm": "@ai-sdk/openai-compatible",
  "name": "DeepSeek (local bridge)",
  "options": { "baseURL": "http://127.0.0.1:8000/v1", "apiKey": "unused" },
  "models": {
    "deepseek-chat":   { "name": "DeepSeek Chat (local bridge)",   "attachment": false, "reasoning": false, "tool_call": true, "temperature": true },
    "deepseek-expert": { "name": "DeepSeek Expert (local bridge)", "attachment": false, "reasoning": false, "tool_call": true, "temperature": true }
  }
},
"modelhub": {
  "npm": "@ai-sdk/openai-compatible",
  "name": "ModelHub",
  "options": { "baseURL": "https://modelhub.134.209.223.63.sslip.io/v1" },
  "models": {
    "gemini-3.1-flash-lite": { "name": "Gemini 3.1 Flash Lite", "attachment": true, "reasoning": true, "tool_call": true, "temperature": true },
    "codestral-latest":      { "name": "Codestral Latest",      "attachment": true, "reasoning": false, "tool_call": true, "temperature": true }
  }
}
```

**`providers` (v2):**
```jsonc
"local-deepseek": {
  "package": "aisdk:@ai-sdk/openai-compatible",
  "settings": { "baseURL": "http://127.0.0.1:8000/v1" },
  "models": {
    "deepseek-chat":   { "name": "DeepSeek Chat (local bridge)",   "attachment": false, "reasoning": false, "tool_call": true, "temperature": true },
    "deepseek-expert": { "name": "DeepSeek Expert (local bridge)", "attachment": false, "reasoning": false, "tool_call": true, "temperature": true }
  }
},
"modelhub": {
  "package": "aisdk:@ai-sdk/openai-compatible",
  "settings": { "baseURL": "https://modelhub.134.209.223.63.sslip.io/v1" },
  "models": {
    "gemini-3.1-flash-lite": { "name": "Gemini 3.1 Flash Lite", "attachment": true, "reasoning": true, "tool_call": true, "temperature": true },
    "codestral-latest":      { "name": "Codestral Latest",      "attachment": true, "reasoning": false, "tool_call": true, "temperature": true }
  }
}
```

### 4.3. Выровнять `providers.amd-radeon` (v2) до 7 моделей

В `opencode.jsonc` блок `providers.amd-radeon` сейчас содержит **3 модели**
(DeepSeek-V4-Flash, Qwen3.8-Flash-Next, MiMo-V2.6-Flash), а `provider.amd-radeon`
(v1) и `mcode.jsonc` — **7** (добавлены: DeepSeek-V4.1-Flash, DeepSeek-V4-Flash-Vision-Exp,
GLM-5.3-Flash, Qwen3.8-27B). Довести `providers.amd-radeon` до тех же 7 моделей,
что в `provider.amd-radeon` (строки 121-134 opencode.jsonc).

## 5. Ключи — вне спека

- M Code держит ключи в **secret-service** (system keyring, sealed, через UI).
- OpenCode — в открытом `~/.local/share/opencode/auth.json` + vault `.env`.
- Реле-провайдеры (apinex, justwoker и др.) — ключи в vault `.env`, M Code
  (AppImage) их не видит. Это **вторая** независимая причина падений, данным
  спеком НЕ лечится. Решение — отдельно владельцем (добавить ключи в
  secret-service через UI M Code).

## 6. Порядок применения

1. Создать `mcode.jsonc` в dotfiles (п.4.1).
2. Дополнить `opencode.jsonc` (п.4.2, п.4.3).
3. Синхронизировать dotfiles (stow или `./stow.sh`), чтобы оба SDK видели конфиг.
4. Перезапуск M Code.
5. Проверка: `mcode models ls` показывает все 8 провайдеров (включая
   `local-deepseek` + `modelhub`).

## 7. Проверка результата (Definition of Done)

- [ ] `mcode.jsonc` создан в dotfiles со всеми 8 провайдерами.
- [ ] `opencode.jsonc` содержит `local-deepseek` + `modelhub` в `provider` и `providers`.
- [ ] `providers.amd-radeon` = 7 моделей (совпадает с `provider.amd-radeon`).
- [ ] JSON валиден (нет синтаксических ошибок — opencode.jsonc допускает комментарии).
- [ ] M Code после перезапуска видит 8 провайдеров (`mcode models ls`).

## 8. Notes / риски

- Править **только** dotfiles; локальный `mcode.jsonc` M Code — зона владельца,
  НЕ трогать (red-line для агентов).
- Ключи не копировать, не логировать, в репо не класть.
- `opencode-go` (default-модель OpenCode) — встроенный канал, в provider-блок
  не добавлять.