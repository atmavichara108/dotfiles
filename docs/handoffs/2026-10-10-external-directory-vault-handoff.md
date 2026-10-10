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

- Vault-root `opencode.json` **в рабочем дереве** на момент инцидента: default
  `* deny`; в allowlist был основной `OpenCode-Vault/**`, но НЕ было sibling
  `OpenCode-Vault-tasks/**` и `/tmp/opencode/**`. Это и дало отказ.
- **Корень (уточнено 2026-10-10 после apply):** нужные строки уже есть в
  `origin/main` Vault (коммит `cac2a00` «permission preflight for worktrees»,
  добавляет `OpenCode-Vault-tasks/**` и `dotfiles-tasks/**`). Но основной рабочий
  checkout Vault стоял на отошедшей от main task-ветке
  `task/pipboy-rebuild-20261009`, чья версия файла эти строки не содержит —
  рабочее дерево отстало от main. Это не «нет фикса», а «checkout устарел».
- SSA worktree `opencode.json` содержит нужный allow; сессия была открыта из
  основного корня, поэтому применялась отставшая версия файла.
- Worktree `git-common-dir` —
  `/home/rudra/Projects/OpenCode-Vault/.git`; common-dir лежит в allowlisted
  основном Vault. Гипотеза о `.git` target вне allow-scope не подтверждена.
- Vault method `02-Methods/incident-fix.md` уже отмечает, что внешние temp-пути
  могут быть закрыты для write-tools.

## Применённый apply (2026-10-10, мандат Рудры)

Рабочее дерево `OpenCode-Vault/opencode.json` восстановлено из `origin/main`
(`git checkout origin/main -- opencode.json`), JSON валиден, обе allow-строки
на месте, секретные `deny` сохранены. Изменение оставлено **uncommitted** в
чужом checkout: коммит в отошедшую task-ветку бессмыслен (строки уже в main),
а переключение/merge чужого dirty-ветки — работа её владельца. Статус live
сессий из корня Vault теперь должен читать правильный файл.

**Остаточный шаг за куратором Vault:** когда task-ветка `pipboy-rebuild`
сольётся в main, её версия `opencode.json` снова затрёт эти строки (diff
HEAD↔origin/main это подтверждает) — при merge нужен conflict-check по этому
файлу, чтобы не откатить `cac2a00`.

Dotfiles-конфиги уже дают общую внешнюю allow с secret-deny; dotfiles не вносит
изменения в Vault. Это handoff, не просьба Максу выполнять команды вручную.
