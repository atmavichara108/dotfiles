# Incident record — инструмент shell скрыт у primary-агента, корень в policies

- **Incident ID:** INC-20
- **ts:** 1792956000 (2026-10-25 23:24); закрыт 2026-10-26 01:00 (по донесению адресата)
- **error class:** permissions-policies-missing-action (+ agent-definition-shadow)
- **source/tool:** глобальный `opencode-global/.config/opencode/opencode.jsonc` (policies)
  + `.opencode/agent/obsidian-servant.md` (двойное определение агента)
- **route_state:** resolved-fix (коммит `5a13804` волта, merge `c9e49f2`)
- **notification_state:** доклад владельцу сделан (письмо 2026-10-25)

## Symptom
После рестарта сессии Служителя Обсидиан (`ses_ea02cc0d8ffeFXUsAX9UeQWs2D`)
инструмент shell/bash не экспонирован:
`No tool named "shell" is currently available.` и `Unknown tool 'bash'` в Code Mode.
При этом `write`/`edit` в `10-Deck/**` работали; `~/.local/share/ship-mail/**`
и `~/.local/bin/**` давали `Permission denied: external_directory`.

## Repro (дословно от адресата, basis: quoted)
TUI-сессия Служителя (не headless run), cwd был `~/dotfiles` — команды
`ship-mail.sh inbox/show/ack/send`, write в ящик получателя, read ящика.
Три рестарта не снимали симптом.

## Root cause (из сверки, не догадка)
1. **Главное:** в глобальном `opencode.jsonc` в `policies` **не было action
   `shell` вообще** — были только deny-строки прочих инструментов. Отсутствие
   allow = инструмент скрыт целиком, и агентский файл (любые bash-правила) на
   это не влияет.
2. **Усиливающее (мой первоначальный промах):** у агента `obsidian-servant` было
   **двойное определение** — проект (`~/Projects/OpenCode-Vault/.opencode/agent/`)
   и глобал (`~/.config/opencode/agent/`, симлинк в dotfiles). При cwd=dotfiles
   эффективным был глобальный файл (allowlist+`"*": deny`), поэтому правка
   `bcbc709f` в проектную копию не давала эффекта — «правка не помогает».
   Победитель между слоями не определён каноном — это дефект.

## Fix
- **Со стороны волта** (сделан адресатом): строка
  `{ "action": "shell", "resource": "*", "effect": "allow" }` в `policies`
  (коммит `5a13804`, merge `c9e49f2`).
- **Проверено сегодня мной:** строка жива в live-конфиге
  `~/.config/opencode/opencode.jsonc:72` (+ deny-лист опасного строки 81–100).

## Evidence
- Живой конфиг: `grep -n '"action": "shell"' ~/.config/opencode/opencode.jsonc`
  → строка 72 `allow`, строки 81–100 deny.
- Волт: `git log --oneline` → `59d8c91a`, `0f9bffa3` (после `5a13804`).
- Дословный симптом и startup-hint — письмо Служителя 2026-10-26T23:24
  (ship-mail, id `064c6a4f63fd`, ref `servant-shell-diagnose-20261026`).

## seen-before
Нет: класс `permissions-policies-missing-action` — новый. Родственный
`agent-definition-shadow` — тоже новый класс (двойное определение агента).

## Открытые хвосты (созданы этим инцидентом)
- Инвариант для Gate 7 / сторожей: каждый инструмент, упомянутый в agent `.md`,
  обязан иметь allow/deny в `policies`; и агентные файлы обязаны быть
  единственного источника (или сознательно разведены). Рекомендация Мастерской
  передана ИЦ письмом 2026-10-27 (`incident-shell-tool-missing`).
