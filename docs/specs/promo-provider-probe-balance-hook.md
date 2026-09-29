---
type: Spec
title: Promo-provider probe + balance hook (dotfiles)
description: Execution spec для dotfiles-агентов: read-only probe и balance monitor промо/реферальных провайдеров. Scope — только dotfiles скрипты/конфиги. Независимо верифицировано 2026-09-29: 41/41 тестов, соответствие exit/smoke/redaction/thresholds/proxy.
tags: [spec, dotfiles, provider, balance-hook, promo-provider]
timestamp: 2026-09-16
status: implemented
---

# Spec: Promo-provider probe + balance hook (dotfiles)

> Владелец исполнения — **dotfiles project agents / sysop**, не librarian.
> Метод и контракт: [[02-Methods/promo-provider-protocol]]. Карточки:
> [[01-Reference/provider-cards/linaliapi]] · [[01-Reference/provider-cards/justwoker]].

## 1. Intent

Read-only наблюдатель за состоянием промо/реферальных провайдеров: периодический
probe (`/v1/models` + smoke-чат на дешёвой модели) и мониторинг usable-баланса.
По умолчанию hook не тратит кредиты и никогда не меняет конфиг. Smoke-chat,
который потенциально расходует кредиты, выполняется только при явном opt-in.

## 2. Scope

**In (dotfiles only):**
- Скрипты/конфиги в `~/dotfiles` для read-only provider probe + balance monitor.
- Обвязка уведомлений (desktop/Telegram adapter опционально).

**Out:**
- Код приложений (не трогать).
- API-ключи в репо/логах (запрещено).
- Автоматические траты и мутация конфига провайдера.

## 3. Inputs

- Provider card/config selector (`provider_id` из
  `01-Reference/provider-cards/`).
- Auth-store ID (должен совпадать с `provider_id`; см.
  [[02-Methods/promo-provider-protocol]] CONNECT).
- Endpoint (`https://…/v1`).

## 4. Commands / HTTP behavior

- `GET /v1/models` с auth (ключ читается из локального auth-store или явно
  заданной переменной окружения, в output не попадает).
- Smoke-чат — только по opt-in и только на явно заданной оператором модели;
  фиксируется факт ответа, не содержимое.
- HTTP — через настроенный прокси, когда провайдер требует (proxy requirement
  из карточки).

## 5. Output (machine-readable JSON)

```json
{
  "provider_id": "justwoker",
  "status": "ACTIVE|DEGRADED|BLOCKED|ERROR",
  "models_count": 0,
  "usable_balance": null,
  "balance_kind": "referral|promotional|paid|null",
  "checked_at": "2026-09-16T00:00:00Z",
  "warnings": ["empty_models", "balance_unknown", "proxy_required"],
  "evidence_refs": ["card:01-Reference/provider-cards/justwoker.md"]
}
```

Секреты **redacted**; ключ не выводится ни в поле, ни в лог.

## 6. Exit statuses

| Exit | Status | Семантика |
|------|--------|-----------|
| 0 | ACTIVE | непустой `data`, smoke ok (если включён), usable balance известен |
| 1 | DEGRADED | отвечает, но balance unknown / smoke failed / proxy обязателен |
| 2 | BLOCKED | нет моделей (`data: []`) / Cloudflare/403/401 на probe |
| 3 | ERROR | сеть/недоступность endpoint/auth-store |

## 7. Thresholds и stale/error semantics

- **Warning thresholds:** 25% / 10% / 0% usable баланса.
- **Stale:** probe не отработал (сеть/4xx/5xx) → статус `DEGRADED`/`ERROR`, не
  «всё ок»; не выдавать ACTIVE при устаревшем/неудачном probe.
- Balance unknown / displayed-only (referral без подтверждённой спендируемости)
  → `usable_balance: null`, warning `balance_unknown`.

## 8. Notification hook contract

- Adapter desktop/Telegram — **опциональный**.
- Без креденшелов в репо; sink настраивается пользователем.
- События: пересечение порога, переход ACTIVE→DEGRADED/BLOCKED, ERROR/stale.

## 9. Acceptance tests

- **Fixture-based, no network** — моки HTTP/auth-store.
- Кейсы: пустой `data: []` → BLOCKED; 401/403 → BLOCKED/DEGRADED; proxy required;
  redaction секретов (нет ключа в JSON/логе); баланс ниже 25/10/0 → warning;
  error/stale → ERROR/DEGRADED.
- **Independent verifier обязателен** перед переводом в implemented.

## 10. Ownership

- Исполнение: **dotfiles project agents / sysop**.
- librarian не реализует.

## 11. Реализация

**Файлы:**
- `scripts/.local/bin/promo-provider-probe` — Python CLI (stdlib + curl subprocess)
- `scripts/.config/promo-provider-probe/config.json` — декларативный конфиг без секретов
- `scripts/tests/test_promo_provider_probe.py` — fixture-based no-network тесты (unittest)

**Opt-in smoke chat:**
- Default OFF (тратит кредиты)
- CLI флаг `--smoke` или конфиг `smoke_chat: true`
- Модель задаётся декларативно: `smoke_model` в конфиге провайдера
- Если `--smoke` без `smoke_model` → DEGRADED warning `smoke_model_not_configured` без запроса

**Balance endpoint декларативно:**
- `balance_endpoint` — путь (например, `/balance`, `/dashboard/billing/usage`)
- `balance_selector` — JSON field для извлечения (например, `balance`, `total_available`)
- `balance_kind` — тип баланса из конфига (`referral`/`promotional`/`paid`), только для подтверждённого usable balance
- `balance_initial` или `balance_total` — denominator для percent thresholds
- Если не настроено → `balance_unknown` без лишних запросов

**Thresholds (percent):**
- 25% → `balance_low`
- 10% → `balance_critical`
- 0% → `balance_zero` + DEGRADED
- При отсутствии denominator не выдавать percentage warnings

**Auth resolution:**
1. Env: `PROMO_PROVIDER_<PROVIDER_ID>_KEY`
2. Auth-store: `~/.local/share/opencode/auth.json` по `provider_id`

**Secret redaction:**
- Ключ не попадает в JSON output, stderr, notify
- curl_request не включает response body в error (может содержать секреты)
- Authorization header не логируется

**Proxy support:**
- Декларативно через `proxy` в конфиге (HTTP/HTTPS/SOCKS via curl)
- Если proxy настроен → warning `proxy_required`

**Тесты:**
- unittest (stdlib, без pytest)
- No-network: моки subprocess.run для curl
- Покрытие: auth resolution, probe models, smoke chat, balance check, thresholds, exit codes, secret redaction, smoke_model validation

## 12. Ссылки

- [[02-Methods/promo-provider-protocol]] — метод и контракт.
- [[01-Reference/provider-cards/linaliapi]] · [[01-Reference/provider-cards/justwoker]]
- [[03-Projects/dotfiles]] · [[TASKS]] T-144, T-145.
- [[04-Memory/session-log/2026-09-16]]
