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
