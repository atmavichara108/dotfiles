---
type: Agent Instructions
title: dotfiles — правила для sysop
description: Конвенции и правила работы с dotfiles через OpenCode.
timestamp: 2026-06-30
---

# dotfiles — Agent Instructions

> Manjaro dotfiles, управляемые через GNU Stow. OpenCode здесь = пульт управления системой, не разработка кода.

## Конвенции

- **Менеджер:** GNU Stow. Каждый конфиг — отдельная директория (zsh/, nvim/, tmux/ и т.д.).
- **Структура:** `директория/.файл` → `stow директория` → симлинк в `$HOME`.
- **Коммиты:** `feat(shell): ...`, `fix(nvim): ...`, `chore: ...`, `docs: ...`
- **Никаких секретов:** ключи, токены, пароли — НЕ в репо. Используй `.env` или отдельные файлы вне git.

## Запрещённые действия

- **НЕ** ставь/удаляй пакеты (`pacman -S`, `yay`, `paru`) — только предлагай команды текстом.
- **НЕ** правь `/etc` — только предлагай изменения.
- **НЕ** меняй права (`chmod`, `chown`) — только предлагай.
- **НЕ** перезапускай сервисы (`systemctl restart`) — только предлагай.
- **НЕ** монтируй/размонтируй файловые системы.

## Архитектура (кратко)

```
dotfiles/
├── stow.sh          # массовый stow всех директорий
├── add-package.sh   # добавить новый пакет конфигов
├── zsh/             # shell конфиги (.zshrc, p10k)
├── nvim/            # Neovim конфиги
├── tmux/            # tmux конфиги + TPM
├── git/             # .gitconfig
├── qtile/           # WM конфиги
├── alacritty/       # терминал
├── rofi/            # лаунчер
├── picom/           # композитор
├── btop/            # мониторинг
├── ...              # остальные пакеты
```

## Окружение

- **OS:** Manjaro (Arch-based)
- **Shell:** zsh + powerlevel10k
- **WM:** Qtile
- **Terminal:** Alacritty
- **Editor:** Neovim

## Команды OpenCode

- `/sysaudit` — аудит системы: софт вне дотфайлов, дрейф конфигов, статус пакетов
