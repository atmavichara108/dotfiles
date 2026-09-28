---
description: Открыть Pip-Boy на вкладке MODELS — переключение моделей агентов.
model: opencode-go/glm-5.3-flash
---

# /agents — дашборд моделей агентов в Pip-Boy

Открой Pip-Boy (подняв хост, если он погашен) с deep-link на вкладку
**MODELS**: таблица всех агентов (глобальные + проектные + встроенные),
у каждого выпадающий список живых моделей.

## Шаги

1. Подними хост и открой браузер на deep-link `#models`:
   ```bash
   python3 ~/Projects/OpenCode-Vault/tools/ecosystem-map/pipboy.py open
   ```
   затем открой `$BROWSER http://127.0.0.1:8123/#models` (или используй
   `~/.local/bin/pipboy-rofi` — строка `agents`).

2. Вкладка читает `/action model-list` и `/action model-models`:
   - агенты из `~/dotfiles/opencode-global/.config/opencode/agent/*.md`,
     `<project>/.opencode/agent/*.md` и `agent.<name>.model` конфигов;
   - модели — объединение `opencode models` (live), `provider.<id>.models`
     (declared), моделей уже стоящих у агентов (in-use) и реестра
     `providers.json` (aliases medium/free).

3. Выбор `<select>` вызывает `/action model-apply` — точечная правка
   `model:` во фронтматтере агента (или agent-блоке конфига) с flock+бэкапом.
   Изменение применяется после **рестарта инструмента / новой сессии** —
   hot-reload модели в движке нет.

## Канон

- Роутер моделей: `02-Methods/model-routing`
- Команда-медиум/фри: `/prov <сокр> <medium|free> [g]`
- Провайдеры: `01-Reference/providers`, `01-Reference/provider-cards/*`
- Бэкенд: `tools/ecosystem-map/model-router.py`, `actions.py (model-*)`