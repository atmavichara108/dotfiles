---
type: Execution Spec
kind: task
title: M Code ↔ OpenCode bridge endpoint
project: dotfiles
task: T-156
status: verified-tech-pass
timestamp: 2026-10-05
---

# T-156 — M Code ↔ OpenCode bridge endpoint

## Цель

Сделать локальный OpenCode v2 service управляемым через user-unit и добавить
безопасную тонкую оболочку для общего контракта M Code и будущего TUI-клиента.
Направление оркестрации: M Code → OpenCode. Обратный незапрошенный push в M Code
не реализуется; асинхронный reverse-канал использует git-дерево.

## Scope

In:

- systemd user-unit в `systemd/.config/systemd/user/` для
  `opencode serve --service` на `127.0.0.1:49374`;
- wrapper в `scripts/.local/bin/` с операциями `prompt`, `read`, `handoff`;
- task-документация и проектная memory-запись после завершения;
- read-only проверка авторизации модели через живой endpoint и SSOT-провайдеров.

Out:

- system-wide `/etc` и root-операции;
- установка пакетов;
- hardcoded token, API keys и их логирование;
- push/injection из OpenCode в M Code;
- физический `systemctl --user enable/start` до отдельного approval.

## Контракт wrapper

Wrapper читает token только из `~/.config/opencode/service.json`, передаёт его
через HTTP Authorization и не выводит token. Он предоставляет:

- `prompt <session-id> <text>` → `POST /api/session/{id}/prompt` с JSON-ключом
  `text`;
- `read <session-id>` → `GET /api/session/{id}/message`;
- `handoff <read|write> ...` → чтение/запись ограниченного git-tree handoff
  артефакта для async reverse-канала.

## Managed service

Unit должен использовать существующий OpenCode v2 binary/service contract,
перезапускаться при сбое и быть устанавливаемым через GNU Stow. Живой orphan
не убивать до отдельного apply-gate; rollback обязан возвращать прежний способ
запуска и не удалять рабочий backend.

## Definition of Done (техническая приёмка — это и есть предмет verifier)

- [x] task-spec присутствует в canonical `docs/specs/`;
- [x] unit-файл проходит `systemd-analyze verify` без запуска сервиса;
- [x] wrapper проходит `bash -n`/shellcheck (если доступен);
- [x] wrapper не содержит токена и не печатает секретные значения;
- [x] auth-схема wrapper соответствует серверу (HTTP Basic `opencode:<password>`);
- [x] prompt/read используют точные v2 endpoint и ключ `text`;
- [x] handoff ограничен git-деревом, symlink-эскейп отклоняется, live push в M Code не обещан;
- [x] авторизация модели проверена живым прогоном без `provider.auth`-ошибки;
- [x] `stow -n scripts` и `stow -n systemd` проходят без конфликтов.

## Lifecycle (после технического PASS, не входит в предмет verifier)

- [ ] изменения закоммичены в `task/*` и получили tag;
- [ ] spec перенесена в `docs/specs/done/`;
- [ ] memory-запись добавлена в `.opencode/memory/` (включая incident-запись);
- [ ] физический apply gated отдельным approval (`systemd-run` detached + пост-чек);
- [ ] ротация пароля `service.json` (после apply) — за оператором.

## Apply gate

Физические `systemctl --user enable/start` не входят в автоматическое
исполнение этой спеки. После verifier PASS и commit/tag оператору показывается
отдельный preflight и запрашивается approval. До него текущий backend остаётся
живым; актуальный PID определяется только через `pgrep -f 'opencode serve --service'`.

## Rollback

1. Не выполнять enable/start при провале preflight.
2. При проблеме после apply — остановить новый user-unit только с отдельным
   approval и вернуть прежний orphan/startup-маршрут.
3. Не удалять `service.json`, существующий backend или auth-конфигурацию.
4. Откатить репозиторные изменения через revert коммита; tag не переписывать.

## Sources

- Vault route-log: `2026-10-01-mcode-bridge-dotfiles.md`.
- Vault audit: `2026-09-30-mcode-opencode-bridge.md` и Addendum 2026-10-01.
