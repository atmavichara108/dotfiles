# Runbook: Markdown Workbench

## Назначение

Единый быстрый workflow для Markdown в терминале: найти файл в Ranger, прочитать его в preview или Glow, открыть в Neovim и редактировать с live-rendering. Исходный `.md` — единственный источник правды; визуальный слой ничего не записывает в него.

## Компоненты

- **Ranger** — навигация и preview через `~/.config/ranger/scope.sh`.
- **Neovim/LazyVim** — редактирование и render-markdown.nvim.
- **render-markdown.nvim** — inline rendering headings, code, tables, checkboxes и conceal-элементов.
- **Glow** — внешний pager/viewer для чтения без запуска Neovim.
- **Treesitter Markdown** — parser для корректного syntax tree и rendering.

Пакеты Stow: `nvim/` и `ranger/`. Реализационные пути перечислены в [спецификации](../specs/markdown-workbench.md).

## Ranger

1. Запустить Ranger и выбрать `.md`.
2. В правой колонке должен появиться Glow-preview; если Glow недоступен — plain text/highlight preview.
3. Для полноэкранного чтения использовать `Mg` (foreground Glow pager).
4. Для редактирования использовать обычное открытие через `${VISUAL:-$EDITOR}`. Не удалять существующие `E`, `i`, `<F4>` и search bindings.

При проблемах preview проверить, что в `rc.conf` включены `use_preview_script` и `preview_script`, а `scope.sh` исполняется текущим Ranger. Preview не обязан поддерживать интерактивный stdin.

## Neovim

Открыть файл штатным `$EDITOR` или `nvim path/to/file.md`. После загрузки Markdown доступны:

| Mapping/command | Назначение |
|---|---|
| `<leader>mp` | `:RenderMarkdown buf_toggle` — toggle rendering текущего буфера |
| `<leader>mP` | `:RenderMarkdown buf_enable` — принудительно включить rendering текущего буфера |
| `<leader>mg` | открыть внешний Glow viewer |
| `:RenderMarkdown toggle` | глобальная диагностическая команда toggle |
| `:RenderMarkdown enable` / `disable` | глобальные диагностические команды включения/выключения |

Mappings `<leader>mp` и `<leader>mP` buffer-local и действуют только в текущем Markdown-буфере. Глобальные команды `:RenderMarkdown toggle`, `:RenderMarkdown enable` и `:RenderMarkdown disable` остаются диагностическим способом проверить загрузку plugin и состояние rendering. В обычном режиме текстовые маркеры могут быть скрыты conceal, но при переходе в Insert и при выключении rendering файл остаётся исходным Markdown.

## Toggle, Glow и fallback

- Toggle меняет только presentation текущего buffer/window.
- Glow читает файл и возвращает pager; он не заменяет `$EDITOR`.
- Нет Glow: Ranger показывает обычный text/highlight preview, а Neovim продолжает редактирование/rendering.
- Нет Treesitter parser: сначала восстановить parser; временный fallback — отключить rendering и работать как с plain Markdown.
- Ошибка render-markdown.nvim: `:RenderMarkdown disable`, сохранить файл обычным способом, затем проверить `:checkhealth`/`:Lazy`.

## Диагностика

### Preview пустой или показывает сырой текст

Проверить по порядку:

1. `command -v glow` и `glow --version`.
2. `~/.config/ranger/scope.sh` — это Stow-ссылка на `ranger/.config/ranger/scope.sh`.
3. `set use_preview_script true` и `set preview_script ~/.config/ranger/scope.sh` в `rc.conf`.
4. Путь с пробелами/кавычками: вызовы должны передавать path отдельным аргументом, без `eval`.
5. Plain fallback: отсутствие Glow не является ошибкой Ranger.

### Rendering не загружается в Neovim

1. Открыть `.md`, выполнить `:Lazy` и найти `render-markdown.nvim`.
2. Проверить глобальную диагностическую команду `:RenderMarkdown toggle`; если команды нет — plugin spec не загрузился.
3. В Markdown-буфере проверить `<leader>mp` → `:RenderMarkdown buf_toggle` и `<leader>mP` → `:RenderMarkdown buf_enable`; если mapping отсутствует, проблема в buffer-local настройке.
4. Проверить `:checkhealth nvim-treesitter` и наличие Markdown parser.
5. Посмотреть `:messages`; не исправлять проблему правкой lock-файла наугад.

### Conceal/Treesitter выглядит неправильно

Conceal зависит от `conceallevel` и типа окна, Treesitter — от parser/runtime ABI. Для диагностики:

- временно проверить `:set conceallevel?` и `:InspectTree`;
- повторно открыть буфер после установки/обновления parser;
- выключить rendering командой `:RenderMarkdown disable` и убедиться, что исходные `#`, `*`, `` ` `` видны;
- не менять документ «для фикса» — это только визуальная диагностика.

## Stow recovery

Источник правды — файлы в `/home/rudra/dotfiles/nvim/` и `/home/rudra/dotfiles/ranger/`, а не симлинки в `$HOME` и не plugin checkout. При конфликте:

1. Не удалять рабочий конфиг и не перезаписывать его вслепую.
2. Выполнить dry-run для соответствующего пакета: `stow -n nvim` или `stow -n ranger`.
3. Найти конфликтующий target и сохранить незнакомое содержимое как backup вне репозитория.
4. Повторно применить только нужный пакет через обычный Stow workflow.
5. Проверить symlink target и smoke tests из спецификации.

Если plugin spec не виден в `$HOME`, исправлять пакет `nvim`, а не редактировать `$HOME/.config/nvim` отдельно: иначе появится drift.

## Source-of-truth

- Конфигурация: `/home/rudra/dotfiles/nvim/.config/nvim/` и `/home/rudra/dotfiles/ranger/.config/ranger/`.
- Контракт: `docs/specs/markdown-workbench.md`.
- Операции: этот runbook.
- Решение и границы: `docs/decisions.md`, ADR-012.
- Не считать source-of-truth: generated preview, Glow output, cache, `~/.local/share/nvim/lazy/`, `$HOME`-файлы после unlink и временные HTML/PDF.

## Обновление плагина

1. Проверить актуальные README/API `render-markdown.nvim`, LazyVim и Glow; особенно commands, `setup(opts)` и Treesitter requirements.
2. Обновить plugin через штатный Lazy workflow и зафиксировать только намеренно изменившийся lock-файл.
3. Сверить public API: глобальные диагностические `:RenderMarkdown toggle`, `enable`, `disable` и buffer-local mappings `<leader>mp` → `:RenderMarkdown buf_toggle`, `<leader>mP` → `:RenderMarkdown buf_enable`.
4. Передать smoke tests verifier: он должен фактически выполнить применимые проверки из спецификации (Neovim headless, Ranger `scope.sh`, Glow с fixture и `stow -n nvim`/`stow -n ranger`) и вернуть PASS/FAIL с результатами; одной ссылки на список тестов недостаточно.
5. Обновить этот runbook и спецификацию, если изменились команды, mappings или fallback; явно сохранить различие глобальных диагностических команд и buffer-local mappings.
6. Если обновление ломает rendering, откатить plugin на предыдущую рабочую версию через Lazy, не подменяя source Markdown и не добавляя аварийный GUI.

## Definition of Done и dirty tree

- `lazy-lock.json` обновлён намеренно до commit render-markdown.nvim, если это нужно для воспроизводимости; lock-файл не считается запрещённым изменением сам по себе.
- Pre-existing unrelated changes в dirty tree не являются дефектом и не удаляются.
- Проверять нужно изменённые файлы по ownership: Markdown Workbench — только `nvim/`, `ranger/` и связанные docs; чужие изменения не включать в оценку.
- Итоговый PASS возможен только после фактического отчёта verifier по применимым smoke tests, проверки buffer-local mappings и проверки ссылок/форматирования docs.
