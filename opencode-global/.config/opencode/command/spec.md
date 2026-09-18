---
description: Прочитать canonical execution spec по spec-home текущего проекта
---

Ты запускаешь единый execution-spec protocol. Selector пользователя: `$ARGUMENTS`.

Единая модель (Vault `docs/specs/README`): каждая execution spec живёт в
репозитории агента, который её исполняет, в `<repo>/docs/specs/`. Vault не
хранит спеки чужих проектов. Единственный кросс-репо указатель — поле
`spec-home` в карточке проекта (`03-Projects/<project>.md`). Исключений нет.

1. Определи текущий project repo и canonical project key (`SERPlux`, `dv-hub`,
   `ChaT`, `AndroidOS`, `dotfiles`, `vault`, …).
2. Прочитай локальные `AGENTS.md` и `README.md` (если существуют).
3. Определи `spec-home` проекта — из карточки Vault
   `/home/rudra/Projects/OpenCode-Vault/03-Projects/<project>.md` (поле
   `spec-home`), либо из локальных `AGENTS.md`/`README.md`. Резолвь spec
   **только внутри `spec-home`**; `..` и пути за пределами каталога запрещены.
4. Если selector пуст, перечисли доступные specs (`spec-home/*.md`) и предложи
   точный вызов `/spec <selector>`; не выбирай spec молча.
5. Если selector задан, разреши его однозначно внутри `spec-home`. Покажи
   absolute canonical path.
6. При отсутствии `spec-home`, недоступности directory/spec или неоднозначности
   selector остановись с `BLOCKED` и точной причиной. Не делай fallback, не
   обращайся к Vault `06-Specs/` и не используй случайные `docs/spec*`.
7. Напомни, что spec — инструкция, а не evidence; его approval, commit/tag и
   verifier gates обязательны.

Верни protocol report: project, `spec-home`, прочитанные local context files,
canonical path, scope/constraints/gates и blockers. Команду не считать
выполнением spec и не создавать/коммитить изменения автоматически.