# Handoff 2026-10-06 — sysop: приём в команду + мандат maya-lint/handshake

- Кто: sysop (dotfiles primary, инфраструктурный агент), ветка `task/maya-lint-handshake`
- Статус: принят в команду «Великий мудрец», регламент team-protocol v1 + peer-comms прочитаны
- Hello: роль — dotfiles-инфра (репо + $HOME read-only, правки только внутри репо);
  границы — без установки пакетов, без /etc и системных сервисов, без chmod/chown,
  без секретов в репо; работа в task-ветке, verifier PASS обязателен, в инструментах ноль LLM
- Мандат: спека maya-lint v2 + спека peer-comms-handshake (рукопожатие hello/ping/bye, TTL 30 мин)
- Артефакты (эта ветка):
  - `tools/peer-comms/hello.sh` — hello/ping/bye, claims.jsonl append-only (bash-dev, smoke 5/5)
  - `tools/peer-comms/smoke.sh` — смок-тест handshake
  - `.gitignore` — claims.jsonl исключён
- Открытый вопрос координатору: артефакты maya-lint v2 (спеки + tools/maya-lint/)
  существуют как чужая незакоммиченная работа (stash `sysop handshake maya-lint-v2`,
  на ветке task/next-20261005-2145) — моя smoke-проверка их будет read-only из stash,
  дублировать файлы в свою ветку не стал во избежание конфликта владения.
  Прошу указать: ждать коммита владельца или переносить в свою ветку.
- Канал ответа: handoff в git-дереве; живое письмо координатору — после явного добра Рудры (HITL на peer-comms write)
