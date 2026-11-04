# Stow-drift в `~/.config/systemd/user` — диагностика (без правок)

- Дата: 2026-11-04
- Автор: ИЦ (Master-enginer)
- Статус: только диагностика и предложение; службы, права и симлинки не менялись.
- Мандат: ЦУ `night-ic` (Р-077), граница «без установки/снятия служб, без прав».

## Симптом

В `~/.config/systemd/user` есть юниты, которые не являются stow-симлинками:
часть — обычные файлы, часть — абсолютные симлинки. `stow -n systemd` видит
конфликты и не может обновить пакет без ручного разбора.

## Факты

### Обычные файлы (не stow)

| Юнит | active | enabled | Источник в dotfiles |
|---|---|---|---|
| `deepseek-bridge.service` (+ `.d/`) | active | enabled | нет |
| `mail-hub-health.service` / `.timer` | timer active | enabled | нет (почтовый хаб) |
| `mail-hub-sync.service` / `.timer` | timer active | enabled | нет (почтовый хаб) |
| `model-watch.service` / `.timer` | timer active | enabled | есть: `tools/model-watch/` |
| `new-api.service` | inactive | disabled | нет |
| `probe.service` / `.timer` | timer active | enabled | есть: `tools/key-rotator/` |

### Абсолютные симлинки (stow их не считает своими)

`captain-panel-bot.service`, `doctrine-flush.service/.timer`,
`graph-regen.service/.timer`, `gravewalk.service/.timer`,
`portal-tg-guard.service`, `release-watch.service/.timer`,
`serp-tg-guard.service`.

### Относительные симлинки (штатный stow)

`awake-while-open`, `dv-tg-guard`, `gatewatch`, `git-prune`, `justwoker-shim`,
`opencode-serve`, `probe-rotator`, `prod-healthcheck`, `proxy-healthcheck`,
`proxy-on-login`, `session-cop`, `syncthing`, `taskchampion-server`, `tg-guard`,
`tmux-tpm-update`, `usb-daemon`, `wake-sweep`, `wal-cycle`, `watch-logs`,
`xdg-desktop-portal`.

## Dry-run stow

`stow -n -v systemd` сообщает конфликты для абсолютных симлинков
(`captain-panel-bot`, `doctrine-flush`, `graph-regen`, `gravewalk`,
`portal-tg-guard`, `serp-tg-guard`) — они указывают на правильные файлы, но
созданы не stow, поэтому пакет не может их перезаписать.

## Риск

1. Правки в `dotfiles/systemd/...` не доезжают до юнитов, созданных абсолютным
   симлинком, если не пересоздать ссылку.
2. Обычные файлы вообще не управляются репозиторием: `./stow.sh` их не видит,
   дрейф не ловится.
3. `model-watch` и `probe` уже имеют источник в `tools/`, но живут копиями —
   расхождение версий невидимо.

## Предложение (не применять без слова владельца)

1. **Абсолютные симлинки** — пересоздать штатным `stow -R systemd` после
   подтверждения; это операция с симлинками, не со службами.
2. **`model-watch`, `probe`** — либо включить в пакет `systemd`, либо стожить из
   `tools/` отдельным пакетом; выбор — за владельцем.
3. **`mail-hub-health`, `mail-hub-sync`** — определить владельца (почтовый хаб)
   и либо упаковать в его репо, либо в dotfiles; сейчас это чужие файлы.
4. **`deepseek-bridge`, `new-api`** — кандидаты на вывод из эксплуатации;
   решение только после слова владельца.
5. Ничего не удалять и не перезапускать до отдельного апрува: граница «службы»
   из мандата.

## Что проверено

- `ls -la ~/.config/systemd/user`
- `systemctl --user is-active/is-enabled` для файловых юнитов
- `stow -n -v systemd` (dry-run, без применения)
- Сверка с `dotfiles/systemd/.config/systemd/user` и `tools/*`
