---
type: Handoff Note
title: T-156 — M Code ↔ OpenCode bridge endpoint
date: 2026-10-06
from: dotfiles / sysop (ses_ef2508bbfffeOjM30M1LVCz5nd)
to: curator / librarian (Vault, ses_f0877a785ffeB5DCVx3HxigTxB)
status: исполнено; один пункт ждёт решения
branch: task/next-20261005-2145
---

# Handoff: T-156 bridge endpoint

## Статус

Исполнено по handoff от librarian (route-log 2026-10-01, ре-верификация 2026-10-05 на v2.0.23).

## Артефакты

- Спека: `docs/specs/done/mcode-opencode-bridge-endpoint.md` (kind: task; тех-DoD + lifecycle + apply-gate + rollback).
- Unit: `systemd/.config/systemd/user/opencode-serve.service`.
- Обёртка: `scripts/.local/bin/opencode-bridge` (`prompt` / `read` / `handoff`).

## Evidence

- auth-схема сервера: только `Authorization: Basic base64("opencode:<password>")`; wrapper исправлен, живой `read` → 200, `openapi` → 117 путей.
- авторизация модели на сервере: живой прогон (session → prompt → assistant) без `provider.auth`.
- handoff: symlink-эскейп за git-root отклоняется.
- apply: detached `systemd-run`; в момент проверки unit был `active`, порт принадлежал управляемому процессу.
- leak-guard (по просьбе оператора): 20/20 оффлайн-тестов; живая проба с реальным паролем → `[REDACTED]`.

## Коммиты и теги (ветка task/next-20261005-2145)

`0bf24ca` unit+wrapper+spec · `066a033` spec→done · `7366119` память+incident · `1ac4be8` meta `write: allow` · `ed36cdb` leak-guard · `08084f5` фикс кэша leak-guard · `7c6ad92` память (apply-результат).
Теги: `t156-bridge-endpoint`, `t156-leak-guard`.

## Открытый вопрос (нужно решение оператора через куратора)

После ротации пароля управляемый юнит `inactive`, порт `:49374` держит backend, поднятый M Code.
Варианты: (а) вернуть сервис под systemd сейчас — короткий разрыв, M Code переподключится сам; (б) оставить до следующего входа. Рекомендация: (а).

## Канал ответа

peer-comms в сессию `ses_ef2508bbfffeOjM30M1LVCz5nd` либо заметка в этой же папке.
