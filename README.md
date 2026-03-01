# Dotfiles

Personal configuration files for Manjaro Linux, managed with GNU Stow.

## 🛠️ Stack

- **OS:** Manjaro Linux
- **WM:** Qtile
- **Shell:** Zsh + Oh My Zsh
- **Terminal:** Tmux + Alacritty
- **Editor:** Neovim (LazyVim config)
- **File Manager:** Ranger
- **Launcher:** Rofi
- **Bar:** Qtile built-in
- **Compositor:** Picom
- **Git TUI:** Lazygit

## 📦 Installation

### Prerequisites

```bash
sudo pacman -S stow git zsh tmux lazyvim ranger lazygit fzf bat eza fd ripgrep \
               qtile alacritty rofi picom dunst nitrogen

**Clone & Deploy**
git clone git@github.com:atmavichara108/dotfiles.git ~/dotfiles
cd ~/dotfiles
./stow.sh

Additional Setup
Wallpapers:
mkdir -p ~/wallpapers
# Add your wallpapers here
# Update path in qtile config if needed

Oh My Zsh:
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

🔄 Update Workflow
cd ~/dotfiles
# Make changes to configs
lazygit  # or use git manually
# Stage → Commit → Push

📁 Structure
dotfiles/
├── alacritty/     # Terminal emulator
├── dunst/         # Notification daemon
├── lazygit/       # Git TUI config
├── nvim/          # Neovim configuration
├── picom/         # Compositor
├── qtile/         # Window manager
├── ranger/        # File manager
├── rofi/          # Application launcher
└── zsh/           # Shell configuration

🎨 Screenshots
Coming soon...

📝 Notes
Qtile layouts optimized for ultrawide monitors
Alacritty uses custom Nord-inspired theme
Ranger has fzf integration for fuzzy search
Zsh configured with custom aliases and functions
---
Managed with ❤️ and GNU Stow

## Zsh Setup

### Install Oh My Zsh
```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
Install Powerlevel10k theme
￼Copygit clone --depth=1 https://github.com/romkatv/powerlevel10k.git \
  ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/themes/powerlevel10k
Install plugins
￼Copy# zsh-autosuggestions
git clone https://github.com/zsh-users/zsh-autosuggestions \
  ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-autosuggestions

# zsh-syntax-highlighting
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git \
  ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting

# fzf-tab
git clone https://github.com/Aloxaf/fzf-tab \
  ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/fzf-tab
Apply dotfiles
￼Copycd ~/dotfiles
stow zsh p10k
source ~/.zshrc
