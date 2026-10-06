---
type: Handoff Note
title: T-156 — apply-gate закрыт после ротации пароля
date: 2026-10-06
from: dotfiles / sysop
to: curator / librarian (Vault)
status: complete
branch: task/next-20261005-2145
---

# T-156 apply result

Оператор подтвердил вариант (а) через librarian: ротация + немедленный перевод под systemd.

- Ротация выполнена без вывода/логирования значения пароля.
- M Code-backed процесс освобождён; `systemctl --user restart opencode-serve.service` выполнен.
- Unit: `active`, `enabled`.
- Managed `MainPID`: `346858`.
- `ss -tlnp`: `127.0.0.1:49374` принадлежит PID `346858`, процесс находится в cgroup `opencode-serve.service`; orphan не остался.
- `opencode-bridge read`: rc 0.
- HTTP Basic auth на `/api/session/active`: 200.

Примечание: первая detached-проверка ownership ошибочно распарсила PID из `ss` (взяла не тот числовой фрагмент), но ручная пост-проверка по полю `users:(...pid=346858...)` совпала с `systemctl MainPID`; это исправленная evidence.

Ответный канал: peer-comms в кураторскую Vault-сессию и эта git-заметка.
