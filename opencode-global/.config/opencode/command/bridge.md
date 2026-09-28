---
description: Запустить Coordination Bridge protocol в текущем репозитории по intent пользователя.
---

Ты запускаешь protocol entrypoint для canonical AndroidOS Coordination Bridge.
Intent пользователя: $ARGUMENTS

Работай в текущем репозитории и не проси пользователя копировать этот текст в
другой чат. Сначала прочитай `AGENTS.md` и `README.md` target repository, затем
прочитай bridge README, task envelope, handoff и последние связанные
evidence/decision artifacts.

## Canonical context

- Canonical path, если доступен: `/home/rudra/Projects/AndroidOS/coordination/bridge/`.
- Если задан Git-backed mirror/clone path, используй его как рабочее зеркало и
  явно покажи этот путь; не создавай второй bridge source of truth.
- Определи relation текущего репозитория: `AndroidOS`, `Vault`, `dotfiles` или
  `other`. Для `other` остановись, если bridge не задаёт явный scoped route.
- Не копируй bridge artifacts между репозиториями. Strategy остаётся в Vault,
  host facts в dotfiles, а bridge хранит protocol references и metadata.

## Protocol gate

1. Извлеки из intent scope, owner, Definition of Done, ограничения и требуемый
   результат. Если данных недостаточно, задай минимальный уточняющий вопрос.
2. Определи только named role, указанную task envelope или handoff. Проверь,
   что role действительно доступна и запущена в текущем repo/runtime. Не
   назначай hardcoded `planner` или `librarian` и не подменяй отсутствующую
   роль `general`.
3. При отсутствии доказуемого named role запиши или сообщи
   `UNROUTABLE`/`BLOCKED`, не выполняй работу и не используй general fallback.
4. До изменения проверь `git status` и текущий `git diff`; не трогай unrelated
   WIP. Покажи proposed route, scope, owner и DoD.
5. Task envelope имеет одного owner. Handoff должен содержать `from`, `to`,
   scope, inputs, DoD и timestamp. Handoff/evidence/decision history
   append-only; correction создаёт новый artifact.
6. Cross-repository references указывай с `repo=`, полным 40-символьным SHA и
   `path=`. Uncommitted state и abbreviated SHA помечай `planned`, а не
   provenance.
7. Не записывай secrets, credentials, profile copies, raw audio или live DB
   payloads. Review выполняется до verifier; reviewer и verifier независимы.
8. После работы снова покажи `git status` и `git diff`, evidence и blockers.
   Commit/push не выполняй без явного approval пользователя.

## Persistence gate

Запись protocol report является частью protocol, а не дополнительным результатом.
Coordinator или named role, которая выполнила task, обязана сама записать
evidence, handoff и status непосредственно в canonical bridge. Пользователь не
переносит reports между чатами или файлами.

Если coordinator/role не может записать artifact в canonical bridge, остановись
с `BLOCKED` или `UNROUTABLE` и верни точный canonical path и причину. Не оставляй
report только в чате, не проси copy-paste и не создавай локальный fallback.

Результат верни как protocol report: relation, intent, scope/owner/DoD, named
route и доказательство запуска, прочитанные artifacts, изменения/diff,
evidence refs, verdict или `UNROUTABLE`/`BLOCKED`, следующий шаг. Если bridge
недоступен, не создавай локальную копию: сообщи точный blocker.
