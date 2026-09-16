---
type: Spec
title: LinaliAPI provider — канонизация в dotfiles + GUI (M Code)
description: Спек задачи подключения провайдера linaliapi к OpenCode TUI и GUI: intent, scope, изменения, acceptance. Статус: implementation done, sync/verification частично за пользователем.
tags: [spec, dotfiles, opencode, provider, linaliapi]
timestamp: 2026-09-06
status: implementation-done-handoff-pending
---

# Spec: LinaliAPI provider — канонизация в dotfiles + GUI

## 1. Intent

Провайдер **LinaliAPI** (OpenAI-совместимый шлюз `https://api.linaliapi.com/v1`) подключён к OpenCode TUI 2026-09-06 (диагностика и история: [[04-Memory/session-log/2026-09-06]], факты: [[04-Memory/facts]] § «Кастомные провайдеры OpenCode / LinaliAPI»). Конфиг изначально был внесён только в живой `~/.config/opencode/opencode.jsonc` вне dotfiles-канона — restow мог его затереть. Спек фиксирует канонизацию блока в dotfiles и его наличие в GUI (M Code Desktop).

## 2. Scope

**In:**
- `~/dotfiles/opencode-global/.config/opencode/opencode.jsonc` — канон провайдера
- `~/.config/opencode/opencode.jsonc` — живой конфиг TUI (уже содержит блок)
- `~/.config/mcode/opencode.jsonc` — конфиг GUI M Code Desktop
- Документация волта: [[01-Reference/providers]], [[01-Reference/global-config]]

**Out:**
- API-ключи — никогда не попадают в git; хранятся только в `~/.local/share/opencode/auth.json` (вне репозиториев)
- Код приложений, модели сверх согласованного набора

## 3. Изменения (single source блока)

Провайдер-блок (единый для всех точек):

```json
"linaliapi": {
  "npm": "@ai-sdk/openai-compatible",
  "name": "LinaliAPI",
  "options": { "baseURL": "https://api.linaliapi.com/v1" },
  "models": {
    "anthropic/claude-opus-5":   { "name": "Claude Opus 5",     "attachment": true, "reasoning": true, "tool_call": true, "temperature": true },
    "openai/gpt-5.6-sol":        { "name": "GPT-5.6 Sol",       "attachment": true, "reasoning": true, "tool_call": true, "temperature": true },
    "openai/gpt-5.6-luna":       { "name": "GPT-5.6 Luna",      "attachment": true, "reasoning": true, "tool_call": true, "temperature": true },
    "google/gemini-3.8-flash":   { "name": "Gemini 3.8 Flash",  "attachment": true, "reasoning": true, "tool_call": true, "temperature": true },
    "z-ai/glm-5.3":              { "name": "GLM 5.3",           "attachment": true, "reasoning": true, "tool_call": true, "temperature": true },
    "deepseek/deepseek-v4-pro":  { "name": "DeepSeek V4 Pro",   "attachment": true, "reasoning": true, "tool_call": true, "temperature": true }
  }
}
```

Правила:
- `apiKey` в options **не хардкодится** — подтягивается из `auth.json` по совпадению ID провайдера (запись `linaliapi`; опечатка `linalinapi` исправлена 2026-09-06).
- Изменение любого конфига вступает после рестарта соответствующего приложения (TUI / M Code держат конфиг в памяти).
- `/connect` сохраняет только ключ — provider-блок обязателен в конфиге.

## 4. Route (исполнение)

- Librarian — оркестратор, правки конфигов — через субагентов `general` с явным scope/acceptance (named `meta` в сессиях не зарегистрирован; решение пользователя от 2026-09-06).
- Верификация после каждой правки: структурная проверка + `jq empty`.

## 5. Статус исполнения

| Шаг | Файл | Статус |
|-----|------|--------|
| TUI live | `~/.config/opencode/opencode.jsonc` | ✅ провайдер внесён (субагент, jq VALID) |
| dotfiles canon | `~/dotfiles/opencode-global/.config/opencode/opencode.jsonc` | ✅ провайдер внесён (субагент, jq VALID) |
| GUI M Code | `~/.config/mcode/opencode.jsonc` | ✅ блок уже присутствовал, подтверждено субагентом (jq VALID) |
| auth.json | `~/.local/share/opencode/auth.json` | ✅ запись `linaliapi` (rename выполнен пользователем) |

**⚠️ Handoff для sysop/dotfiles pipeline:** живой `~/.config/opencode/opencode.jsonc` — **обычный файл**, не stow-симлинк. Сейчас dotfiles-копия и живая копия обе содержат провайдера, но это два физических файла. Librarian не выполняет dotfiles/stow-операции.

```bash
cd ~/dotfiles && stow --adopt opencode-global
```

`--adopt` может принять урезанный live-файл и потерять permission-профиль dotfiles, поэтому его нельзя запускать вслепую. Нужен точечный sysop/dotfiles run с backup, сравнением и rollback. Перед этим — `git diff` в dotfiles и отдельный коммит канона. **Не выполняется из Vault.**

## 6. Acceptance

- [x] `provider.linaliapi` (6 моделей, без apiKey) присутствует в dotfiles-каноне — jq VALID
- [x] Провайдер виден в `/models` TUI (подтверждено пользователем после рестарта #2 — из проектного/глобального конфига)
- [x] GUI: блок в `~/.config/mcode/opencode.jsonc` подтверждён субагентом — jq VALID
- [ ] **TUI:** после sysop/dotfiles handoff + рестарт — провайдер продолжает резолвиться (симлинк не сломал конфиг)
- [ ] **GUI:** `/models` в M Code показывает `linaliapi/*` после рестарта GUI `[проверить: auth-стор M Code — если 401, ключ добавить через /connect в GUI]`
- [ ] Ключи не в git: auth.json вне репо, dotfiles-коммит содержит только config-блок без секретов

## 7. Ссылки

- История задачи: [[04-Memory/session-log/2026-09-06]]
- Факты: [[04-Memory/facts]] § Кастомные провайдеры OpenCode / LinaliAPI (2026-09-06)
- Справочники: [[01-Reference/providers]], [[01-Reference/global-config]], [[01-Reference/mcode-desktop]]
- Карточка проекта: [[03-Projects/dotfiles]]
