#!/bin/bash

# Скрипт для автоматического stow всех пакетов

DOTFILES_DIR="$HOME/dotfiles"
cd "$DOTFILES_DIR" || exit

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color
BLUE='\033[0;34m'

echo -e "${BLUE}🔗 Stowing dotfiles from $DOTFILES_DIR${NC}\n"

# Массив с пакетами для stow
packages=(

  "zsh"
  "nvim"
  "ranger"
  "git"
  "lazygit"
  "fzf"
)

# Stow каждый пакет
success=0
failed=0

for package in "${packages[@]}"; do
  if [ -d "$package" ]; then
    echo -n "Stowing $package... "
    if stow -v -t "$HOME" "$package" 2>/dev/null; then
      echo -e "${GREEN}✓${NC}"
      ((success++))
    else
      echo -e "${RED}✗ (already stowed or conflict)${NC}"
      ((failed++))
    fi
  else
    echo -e "${RED}✗${NC} Package $package not found"
    ((failed++))
  fi
done

echo -e "\n${BLUE}Summary:${NC}"
echo -e "${GREEN}✓ Success: $success${NC}"
[ $failed -gt 0 ] && echo -e "${RED}✗ Failed: $failed${NC}"

echo -e "\n${BLUE}💡 Tip:${NC} Use ${GREEN}stow -R <package>${NC} to restow"
echo "✨ Done!"
