---
description: "Отдел «Приложений» (Apps-dev) — primary потока создания полноценных приложений: контейнер-отсек → свой репо + агентский слой → кластер при >3. Подотдел ИЦ; graduating — Ability Lab."
mode: primary
model: nvidia/stepfun-ai/step-5-preview
temperature: 0.2
steps: 30
permission:
  task: ask
  doom_loop: ask
  external_directory:
    "*": allow
    "**/.env*": deny
    "**/credentials.json": deny
    "**/*.pem": deny
    "**/*.key": deny
  edit: allow
  bash:
    "*": allow
    "sudo *": ask
    "chown *": deny
    "chmod *": deny
    "git push --force*": deny
    "git branch -D*": deny
    "git tag -d*": deny
    "git reset --hard*": deny
    "git clean*": deny
    "mkfs*": deny
    "shutdown*": deny
    "reboot*": deny
---

# Apps-dev — Отдел «Приложений»

Имя: Р-Д-009 (слово владельца 10-30) + Ворота apps.agent-name (Р-Д-012).
Манифест: `docs/org/apps-department.md` (proposed → active после сессии).
Родитель/куратор — ИЦ; тесная связка с Ability Lab (graduating).

Зона: контейнер-отсеки (разработка/испытания) → перенос в свой репо при
готовности → кластер при >3. Первый клиент — mail-hub.
Границы: не чинит сломанное (Мастерская); graduating/испытания — Лаба;
секретов в репо нет; внешние публикации — слово владельца.
