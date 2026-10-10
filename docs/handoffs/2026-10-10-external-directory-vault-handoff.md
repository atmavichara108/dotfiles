# Handoff — external_directory в Vault SSA worktree

- **Отправитель:** sysop / dotfiles
- **Получатель:** куратор/владелец OpenCode-Vault (отдельный от сессии-источника
  письма; прямой session ID в BAGFIX-LETTER не указан, поэтому peer-comms-письмо
  не отправлялось).
- **Статус:** передано как артефакт; runtime причина `[проверить]`, не объявлено fixed.
- **Task:** BF-20261010-01 / мастерская INC-5.
- **Источник:** вложение Rudra `bugfix-extdir-and-rule-20261010.txt` (текст
  подписан librarian/Vault); payload не дублируется в runtime logs.

## Symptom / repro

По письму от 2026-10-10, в librarian-сессии с workspace
`/home/rudra/Projects/OpenCode-Vault`:

1. Из `/home/rudra/Projects/OpenCode-Vault-tasks/ssa-bootstrap-20261010`
   `git push -u origin task/ssa-bootstrap-20261010` и даже
   `git remote get-url origin` завершались
   `permission.rejected: Permission denied: external_directory`; `git add` и
   `git commit` из того же cwd до этого прошли.
2. `write` в `/tmp/opencode/<file>` давал тот же permission rejection; shell
   write в этот каталог проходит.
3. Push с workspace-root через refspec прошёл.

## Sourced evidence / ведущая гипотеза

- Vault-root `opencode.json`: `external_directory` default `* deny`; allowlist
  содержит `/home/rudra/Projects/OpenCode-Vault/**`, но не sibling
  `/home/rudra/Projects/OpenCode-Vault-tasks/**` и не `/tmp/opencode/**`.
- SSA worktree `opencode.json` содержит allow для
  `/home/rudra/Projects/OpenCode-Vault-tasks/**`; однако сообщённый workspace
  root — основной Vault, поэтому ещё нужно подтвердить, какой project config
  применился к live-вызовам.
- Worktree `git-common-dir` —
  `/home/rudra/Projects/OpenCode-Vault/.git`; common-dir лежит в allowlisted
  основном Vault. Гипотеза о `.git` target вне allow-scope не подтверждена.
- Vault method `02-Methods/incident-fix.md` уже отмечает, что внешние temp-пути
  могут быть закрыты для write-tools.

## Рекомендуемая проверка владельцем Vault

Провести минимальный live repro отдельно для target write, `git remote get-url`
и push из workspace-root/worktree; зафиксировать effective workspace/config и
конкретный проверяемый path. После этого обновить **Vault-owned** allowlist для
необходимого sibling-worktree/temp scope, сохранив deny секретов, затем
повторить repro через инструмент, который ранее блокировался.

Dotfiles-конфиги уже дают общую внешнюю allow с secret-deny; dotfiles не вносит
изменения в Vault. Это handoff, не просьба Максу выполнять команды вручную.
