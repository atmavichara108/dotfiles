---
type: Spec
title: Promo-provider probe + balance hook (dotfiles)
description: Execution spec для dotfiles-агентов: read-only probe и balance monitor промо/реферальных провайдеров. Scope — только dotfiles скрипты/конфиги. Hook planned, не реализован.
tags: [spec, dotfiles, provider, balance-hook, promo-provider]
timestamp: 2026-09-16
status: planned
---

# Spec: Promo-provider probe + balance hook (dotfiles)

> Владелец исполнения — **dotfiles project agents / sysop**, не librarian.
> Реализация в этой задаче НЕ выполняется. Метод и контракт:
> [[02-Methods/promo-provider-protocol]]. Карточки:
> [[01-Reference/provider-cards/linaliapi]] · [[01-Reference/provider-cards/justwoker]].

## 1. Intent

Read-only наблюдатель за состоянием промо/реферальных провайдеров: периодический
probe (`/v1/models` + smoke-чат на дешёвой модели) и мониторинг usable-баланса.
Hook не тратит кредиты и не меняет конфиг.

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

- `GET /v1/models` с auth (ключ читается только из локального auth-стора, в
  output не попадает).
- Smoke-чат на самой дешёвой/безопасной модели — факт ответа, не содержимое.
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
| 0 | ACTIVE | непустой `data`, smoke ok, usable balance известен |
| 1 | DEGRADED | отвечает, но `data: []` / balance непригоден / proxy обязателен |
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
- librarian не реализует. В этой задаче — только spec (planned).

## 11. Ссылки

- [[02-Methods/promo-provider-protocol]] — метод и контракт.
- [[01-Reference/provider-cards/linaliapi]] · [[01-Reference/provider-cards/justwoker]]
- [[03-Projects/dotfiles]] · [[TASKS]] T-144, T-145.
- [[04-Memory/session-log/2026-09-16]]
