#!/bin/bash
DOTFILES_DIR="$HOME/dotfiles"
cd "$DOTFILES_DIR" || exit

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'
BLUE='\033[0;34m'

echo -e "${BLUE}🔗 Stowing dotfiles from $DOTFILES_DIR${NC}\n"

packages=(
  "zsh" "p10k" "tmux" "alacritty"
  "nvim"
  "qtile" "picom" "rofi" "dunst" "x11" "gtk"
  "ranger"
  "git" "lazygit"
  "htop" "btop" "bat" "neofetch" "shell"
  "wal" "wallust" "tinted-theming"
  "flameshot" "copyq" "nitrogen" "thefuck" "weathr" "screenlayout"
  "taskwarrior" "task-tools" "calcurse"
  "xdg" "environment.d" "systemd" "proxyctl"
  "scripts"
  "opencode-global"
)

success=0
failed=0

for package in "${packages[@]}"; do
  if [ -d "$package" ]; then
    echo -n "Stowing $package... "
    if stow -t "$HOME" "$package" 2>/dev/null; then
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
