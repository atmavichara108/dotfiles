# Спецификация: Markdown Workbench

**Статус:** контракт первого этапа, 2026-08-17
**Связанный ADR:** [ADR-012](../decisions.md#adr-012-markdown-workbench)

## 1. Цель и инварианты

Markdown должен одинаково удобно читаться и редактироваться из terminal-native цепочки:

```text
Ranger (навигация/preview) → Glow (полноэкранный просмотр) → Neovim (редактирование/live render)
```

Инварианты:

- source-of-truth — только исходный файл `.md`;
- render не пишет HTML, временный Markdown или изменения в файл;
- отсутствие optional-инструмента не ломает основной инструмент;
- конфигурация остаётся Stow-модульной и живёт в существующих пакетах;
- mappings не должны скрыто переопределять существующие рабочие клавиши.

## 2. Контракт путей

| Назначение | Путь в репозитории | Живой путь |
|---|---|---|
| LazyVim plugin spec | `nvim/.config/nvim/lua/plugins/markdown-workbench.lua` | `~/.config/nvim/lua/plugins/markdown-workbench.lua` |
| Neovim mappings (если вынесены отдельно) | `nvim/.config/nvim/lua/config/keymaps.lua` | `~/.config/nvim/lua/config/keymaps.lua` |
| Ranger settings | `ranger/.config/ranger/rc.conf` | `~/.config/ranger/rc.conf` |
| Ranger preview dispatcher | `ranger/.config/ranger/scope.sh` | `~/.config/ranger/scope.sh` |
| Ranger open actions | `ranger/.config/ranger/rifle.conf` | `~/.config/ranger/rifle.conf` |

Не создавать параллельный `markdown/`-пакет и не править `README.md` или `docs/roadmap.md` в рамках этой спецификации.

## 3. Компоненты и актуальные API

### 3.1 render-markdown.nvim

Источник API: [README/API проекта](https://github.com/MeanderingProgrammer/render-markdown.nvim). На момент реализации сверить README и установленный commit перед использованием.

- Plugin id: `MeanderingProgrammer/render-markdown.nvim`.
- LazyVim-совместимый spec: `{ "MeanderingProgrammer/render-markdown.nvim", ft = { "markdown" }, opts = {} }`; Quarto намеренно не входит в пользовательский scope.
- Основная точка настройки: `require("render-markdown").setup(opts)`; предпочтительно передавать `opts` через Lazy вместо ручного вызова.
- Публичные глобальные user commands для диагностики состояния: `:RenderMarkdown toggle`, `:RenderMarkdown enable`, `:RenderMarkdown disable`.
- Buffer-local mappings используют публичные buffer-команды `:RenderMarkdown buf_toggle` и `:RenderMarkdown buf_enable`, а не внутренние модули плагина. Это снижает риск поломки при обновлении API.
- Render включается только для Markdown-буферов; не добавлять глобальный render во все filetype.

### 3.2 Glow

Источник API: [charmbracelet/glow README](https://github.com/charmbracelet/glow). Glow — CLI, поэтому контрактом являются его флаги, а не внутренний Go API:

- файл: `glow --pager <file.md>`;
- stdin: `... | glow --pager`;
- полезные опции: `--style auto|dark|light|notty`, `--width N`, `--pager/--no-pager`;
- вызов из Ranger должен передавать путь как отдельный shell-аргумент (`-- "$path"`), не интерполировать его без кавычек;
- если `glow` отсутствует, внешний просмотр не запускается, а preview продолжает обычный текстовый путь.

### 3.3 Ranger

Контракт Ranger: `set preview_script ~/.config/ranger/scope.sh`, `set use_preview_script true`, scope получает `$1` path, `$2` width, `$3` height, `$4` cache path, `$5` preview-images flag и возвращает коды 0–7 согласно API `scope.sh`.

- Для `.md`/`text/markdown` сначала пробовать Glow без pager в preview (`glow --style auto --width "$width" --pager=false -- "$path"`), ограничивая вывод `maxln`.
- Код `0` — отрендеренный preview; при ошибке Glow — код `2` и plain-text fallback (или существующий highlight fallback).
- Отдельная клавиша запускает pager-режим Glow; она не должна менять `$EDITOR`/rifle default.
- Фактическая Ranger mapping: `map Mg shell -w glow --pager -- %f` — foreground Glow pager для выбранного файла.
- Фактическая `rifle.conf` action: `ext md|markdown, has glow, label glow = glow --pager -- "$1"`; при отсутствии Glow первым остаётся `mime ^text, label editor = ${VISUAL:-$EDITOR} -- "$@"`.

### 3.4 LazyVim

LazyVim импортирует `lua/plugins` через существующий `nvim/.config/nvim/lua/config/lazy.lua`. Не менять bootstrap и не дублировать `require("lazy").setup`. Plugin spec должен быть отдельным файлом и использовать `opts`, `ft`/event для ленивой загрузки.

## 4. Mappings

Добавить только после проверки существующих LazyVim mappings и `ranger/rc.conf`:

| Контекст | Mapping | Действие |
|---|---|---|
| Neovim Markdown | `<leader>mp` | `:RenderMarkdown buf_toggle` — toggle текущего буфера |
| Neovim Markdown | `<leader>mP` | `:RenderMarkdown buf_enable` — принудительно включить в текущем буфере |
| Neovim Markdown | `<leader>mg` | `:Glow` или `:terminal glow --pager -- <file>` — внешний просмотр |
| Ranger | `Mg` | `shell -w glow --pager -- %f` — foreground Glow pager для выбранного файла |

`<leader>mg` обязан корректно сообщить об отсутствии Glow. Для Ranger не переиспользовать занятые `gm`, `gM`, `<C-g>` и существующие paste/search bindings без явного решения и документации конфликта. Если `:Glow` недоступна, использовать `vim.ui.open`/`vim.system`-совместимый fallback только в рамках Neovim-конфига, без нового скрипта.

Команды `:RenderMarkdown toggle`, `:RenderMarkdown enable` и `:RenderMarkdown disable` остаются глобальными диагностическими командами. Mappings `<leader>mp` и `<leader>mP` buffer-local и применяются только к текущему Markdown-буферу.

## 5. Fallback и отказоустойчивость

Порядок:

1. Neovim + render-markdown.nvim: редактирование работает даже при отсутствии Glow.
2. Ranger + `scope.sh`: Glow preview → обычный highlight/plain text.
3. Ranger pager mapping: Glow → `rifle`/`$EDITOR` для редактирования.
4. Отсутствие Treesitter Markdown: синтаксис/редактирование остаются доступны, rendering деградирует до plain buffer.
5. Ошибка плагина: отключить rendering командой `:RenderMarkdown disable`, не восстанавливать чужую тему и не менять исходник.

Запрещены shell-строки с неэкранированным `$path`, `eval` для пользовательского пути, silent failure и fallback на DoomOne/чужую палитру.

## 6. Smoke tests реализации

Все smoke tests выполняются verifier после реализации. Они не считаются выполненными только потому, что перечислены в этом документе; отчёт verifier должен содержать фактический результат. Пользователь не является ручным CI:

1. `stow -n nvim` и `stow -n ranger` — нет конфликтов.
2. `nvim --headless '+Lazy! sync' '+qa'` — spec парсится и Lazy завершается без ошибки (если sync не требуется, использовать эквивалентную headless-проверку установленной версии).
3. `nvim --headless +'lua print(vim.fn.exists(":RenderMarkdown"))' +qa` — команда доступна после загрузки Markdown plugin.
4. Создать временный Markdown вне репозитория, открыть Neovim, проверить глобальные диагностические `toggle`/`enable`/`disable`, buffer-local mappings `buf_toggle`/`buf_enable` и отсутствие изменений исходного файла (`git diff --no-index`/checksum).
5. `shellcheck` неприменим к `scope.sh` без shebang bash; выполнить `sh -n ranger/.config/ranger/scope.sh` и smoke с Markdown-файлом, проверив non-empty output.
6. При наличии Glow: `glow --pager=false --width 80 -- <fixture>` возвращает 0; без Glow проверить plain-text fallback.
7. Ranger headless/минимальный запуск с test HOME: `scope.sh <fixture> 80 24 <cache> True` не падает и возвращает допустимый код.
8. Проверить конфликт mappings через `:verbose map <leader>mp`/`:verbose map <leader>mg` и визуально проверить `Mg` в Ranger.

## 7. Запреты scope

- Не менять `README.md`, `docs/roadmap.md`, `docs/deferred.md`.
- Не редактировать `opencode.json`, `.opencode/agent/`, `/etc/` или системные сервисы.
- Не устанавливать пакеты и не выполнять `pacman`, `yay`, `paru`.
- Не добавлять секреты, telemetry, сетевые вызовы или GUI runtime.
- Не менять существующие не-Markdown mappings без отдельного ADR.
- Не коммитить plugin checkout, generated HTML, cache, `__pycache__` или lock-файл без отдельного решения.

## 8. Definition of Done

- [ ] Plugin spec находится в указанном Stow-пути и загружается только для Markdown/совместимых буферов.
- [ ] render-markdown.nvim настроен через актуальный публичный API; глобальные диагностические `toggle`, `enable`, `disable` и buffer-local `buf_toggle`, `buf_enable` работают.
- [ ] Treesitter Markdown parser и conceal-поведение проверены; отключение conceal не ломает редактирование.
- [ ] Glow используется для внешнего pager-просмотра и не является обязательным для Neovim/Ranger.
- [ ] Ranger preview использует `scope.sh`, корректно экранирует пути и имеет plain-text fallback.
- [ ] Все mappings уникальны, задокументированы и не ломают текущие Ranger bindings.
- [ ] Source-of-truth остаётся `.md`; generated artifacts отсутствуют.
- [ ] Verifier фактически выполнил все применимые smoke tests, включая `stow -n nvim` и `stow -n ranger`, и вернул результаты.
- [ ] Dirty tree оценён по ownership: pre-existing unrelated changes не являются дефектом и не удаляются; проверяются только изменённые файлы, относящиеся к Markdown Workbench, и запрещённые пути не затрагиваются.
- [ ] Runbook обновлён и явно различает фактические buffer-local mappings (`buf_toggle`/`buf_enable`) и глобальные диагностические команды (`toggle`/`enable`/`disable`).
