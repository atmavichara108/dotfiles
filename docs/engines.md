# Реестр SDK-движков (артефакт формулы портируемости)

> Владелец: ИЦ. Механизм отмирания: строка закрывается вместе с удалением
> dotfiles-пакета движка. Спека-канон: `docs/specs/mcode-coexistence.md`
> (ADR, approved-review 2026-10-17). Формула: новый движок = зона движка +
> dotfiles-пакет (в stow.sh) + SSOT-исходник + скрипт доставки + точка моста +
> строка здесь. Ноль правок в чужих зонах.

| Движок | Зона (только чтение для нас) | SSOT-исходник (dotfiles) | Доставка | Мост | Границы/примечания |
|---|---|---|---|---|---|
| opencode (ядро корабля) | `~/.config/opencode` → `dotfiles/opencode-global`; `~/.local/share/opencode` | `opencode.jsonc` | stow (`opencode-global`) | `opencode-serve.service` :49374 (T-156) | — |
| mcode (M Code Desktop, форк) | `~/.config/ai.mcode.desktop.dev`; `~/.local/share/{mcode,m-code-data}`; `~/.cache/mcode` | `mcode.jsonc` (opencode-global) | `sync-mcode-config.sh` (diff-first, .bak) | клиент моста → :49374 | ADR-019 (глобальные плагины не исполняет); своя БД сессий (Lineage-граница, И-53); правка движка запрещена (И-33). Легаси: замороженная копия `m-code-data/config/opencode.jsonc` (05.09) — НЕ источник. Симлинк `~/.config/mcode` → opencode-global: неактивный канал, кандидат на удаление по evidence (ЦУ 17.10 — не удалять) |

## Открытые точки
- Kill-criterion D2в: подтвердить источник чтения mcode после обновления 15.10
  (logs/strace разово) при первом живом прогоне `sync-mcode-config.sh`.
