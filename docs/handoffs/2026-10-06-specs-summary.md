---
type: Handoff Note
title: Execution specs — итог серии финализации
date: 2026-10-06
from: dotfiles / sysop
to: curator / librarian (Vault)
status: partial-complete; linaliapi GUI pending
branch: task/next-20261005-2145
---

# Итог по execution specs

## Закрыты и перенесены в `docs/specs/done/`

- `peer-comms-handshake.md` — static verifier PASS, live two-party gate PASS
  со стороны librarian; canonical `tools/peer-comms/hello.sh` + `smoke.sh`,
  ack/TTL/bye, ADR-020.
- `pipboy-hotkey.md` — живой binding + py_compile PASS; false-positive `PATH`
  verifier зафиксирован (реальный `~/.local/bin/pipboy-rofi` доступен).
- `mcode-opencode-provider-ssot.md` — ранее status done, физически перенесён.
- `telemetry-p0-spec.md` — ранее status done, физически перенесён.
- `promo-provider-probe-balance-hook.md` — независимый verifier PASS, 41/41,
  redaction/no-spend/stow acceptance.
- `chromium-happ.md` — независимый verifier PASS: wrapper, desktop entry,
  Qtile, Ranger, stow, mock modes; добавлен status done и перенесён.

## Оставлено pending

- `linaliapi-provider-canon.md` — только GUI post-restart acceptance; handoff:
  `docs/handoffs/2026-10-06-linaliapi-gui-check.md`.

## Не трогалось по явному scope

- `coordination-bridge-freeze.md` — frozen by user.
- `maya-lint-v2.md` — `kind: contract`, владелец maya-ветки; вне execution-очереди.

## Commits

T-handshake: `fa0bfe0`, `35715df`, tag `t-handshake-peer-comms`.
Pipboy: `cd81900`. Done transfers: `3a97b6a`, `3f0b4fa`, `576f1ab`.

Vault peer-comms method обновляется куратором по этим фактам.
