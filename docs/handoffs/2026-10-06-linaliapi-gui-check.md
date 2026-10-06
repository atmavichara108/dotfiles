---
type: Handoff Note
title: LinaliAPI provider — GUI acceptance pending
date: 2026-10-06
from: dotfiles / sysop
to: operator via curator / librarian
status: pending-gui-acceptance
---

# LinaliAPI — что проверить в M Code

Репозиторная реализация завершена и не менялась в этой серии:
`~/.config/opencode/opencode.jsonc`, `~/.config/mcode/opencode.jsonc` и
канонический dotfiles-конфиг указывают на один Stow-источник; блок
`provider.linaliapi` присутствует без `apiKey`.

Оператору в GUI M Code нужно только:

1. Полностью перезапустить M Code.
2. Открыть список моделей `/models`.
3. Убедиться, что видны модели `linaliapi/*`.
4. Если GUI показывает 401 — выполнить подключение провайдера через штатный
   GUI `/connect`, не записывая ключ в dotfiles и не присылая его в чат.

До этой проверки spec остаётся в `docs/specs/linaliapi-provider-canon.md` со
статусом `implementation-done-handoff-pending`; в `done/` не переносится.
