---
type: Execution Spec
title: Coordination Bridge freeze
project: dotfiles
status: frozen
timestamp: 2026-08-30
---
# Coordination Bridge freeze

## Decision

По подтверждённому решению пользователя заморозить Coordination Bridge и весь
связанный cross-repo workflow. Bridge не является обязательным шагом для
AndroidOS и не вызывается.

## Frozen scope

- T-108 `system-ops` / permission-root smoke и весь T-108/system-ops execution
  path frozen; не активировать и не продолжать permission experiments.
- T-109 Coordination Bridge integration frozen; bridge artifacts остаются
  historical frozen evidence, не объявляются PASS и не удаляются.
- T-110 optional MCP facade frozen/deferred вместе с bridge integration.
- Не выполнять root, sudo, system mutation, Stow apply, MCP setup или runtime
  permission changes.
- Не создавать новые bridge commands, skills или agents для обхода freeze.

## Resume conditions

Возобновление возможно только после отдельного явного user decision, нового
scope и нового canonical spec/approval gate. Само наличие старого WIP, pending
evidence или permission hypothesis не является основанием для resume.

## Allowed local path

Обычная работа в dotfiles допускается независимо от bridge. Для отдельной
потребности пользователь может открыть dotfiles и выполнить read-only
`/sysaudit <intent>`; этот audit не обязан писать отчёт в AndroidOS или Vault.
