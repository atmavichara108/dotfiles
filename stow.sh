#!/bin/bash
DOTFILES_DIR="$HOME/dotfiles"
cd "$DOTFILES_DIR" || exit

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'
BLUE='\033[0;34m'

echo -e "${BLUE}🔗 Stowing dotfiles from $DOTFILES_DIR${NC}\n"

# --- Repo-local tools verification (dry-run sync entrypoint) ---
# tools/peer-comms is NOT stowed; verify presence, exec bits and syntax before stow.
verify_tools() {
  local tools_ok=0
  local tools_fail=0

  echo -e "${BLUE}🔍 Verifying canonical tools (dry-run)...${NC}"

  for script in tools/peer-comms/hello.sh tools/peer-comms/smoke.sh; do
    if [[ -f "${script}" ]] && [[ -x "${script}" ]]; then
      echo -e "  ${GREEN}✓${NC} ${script} present and executable"
      (( ++tools_ok ))
    else
      echo -e "  ${RED}✗${NC} ${script} missing or not executable"
      (( ++tools_fail ))
    fi
  done

  for script in tools/peer-comms/hello.sh tools/peer-comms/smoke.sh; do
    if bash -n "${script}" 2>/dev/null; then
      echo -e "  ${GREEN}✓${NC} ${script} syntax OK"
      (( ++tools_ok ))
    else
      echo -e "  ${RED}✗${NC} ${script} syntax error"
      (( ++tools_fail ))
    fi
  done

  echo -e "${BLUE}Tools dry-run:${NC} ${GREEN}${tools_ok} checks passed${NC}"
  if (( tools_fail > 0 )); then
    echo -e "${RED}⚠ ${tools_fail} checks failed${NC}"
    return 1
  fi
}

verify_tools || exit 1

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
