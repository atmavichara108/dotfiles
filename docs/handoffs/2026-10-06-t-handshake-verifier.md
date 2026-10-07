---
type: Handoff Note
title: T-handshake — canonical implementation и verifier PASS
date: 2026-10-06
from: dotfiles / sysop
to: curator / librarian (Vault)
status: verifier-pass; live-smoke blocked by runtime HITL
branch: task/next-20261005-2145
---

# T-handshake verifier handoff

## Canonical ownership

По решению оператора выбран вариант A: canonical — `tools/peer-comms/hello.sh` и
`smoke.sh` из активной task-ветки; Python-дубликат убран в именованный stash.
ADR-020 переписан под фактическую Bash+jq реализацию.

## Verifier PASS

- `bash -n`: hello, smoke, stow.sh — PASS.
- shellcheck — PASS.
- smoke: 10/10 — hello/ping, ack, bye, TTL, unknown.
- JSONL append-only, malformed lines пропускаются, ack-state детерминирован.
- `stow.sh verify_tools()` проверяет наличие, executable и syntax canonical tools.
- `.gitignore` исключает runtime claims.
- maya-lint/M Code/linaliapi не затронуты.

## Live gate

Попытка live two-party write (sysop → librarian) через OpenCode v2 API была
остановлена runtime permission gate: non-interactive shell не может подтвердить
mutating action в чужой сессии. Обход gate запрещён.

Нужен интерактивный запуск у куратора/librarian:

1. hello обеих реальных сессий с общим временным `CLAIMS_FILE`;
2. короткое письмо B→A с ACK;
3. `ack --session <recipient> --from <sender>`;
4. `ping --json` подтверждает `op: ack`, `status: active`;
5. `bye` и TTL smoke;
6. после этого передать evidence обратно в peer-comms/git.

До этого commit/tag canonical implementation не финализируются как complete.
