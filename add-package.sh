#!/bin/bash
# Добавление нового package в dotfiles

if [ $# -lt 2 ]; then
  echo "Usage: ./add-package.sh <package-name> <config-path>"
  echo ""
  echo "Examples:"
  echo "  ./add-package.sh kitty .config/kitty"
  echo "  ./add-package.sh tmux .tmux.conf"
  echo "  ./add-package.sh vim .vimrc"
  exit 1
fi

PACKAGE=$1
CONFIG_PATH=$2
DOTFILES="$HOME/dotfiles"
SOURCE="$HOME/$CONFIG_PATH"
DEST="$DOTFILES/$PACKAGE"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}📦 Adding $PACKAGE to dotfiles${NC}\n"

# Проверка существования source
if [ ! -e "$SOURCE" ]; then
  echo -e "${RED}✗ Error: $SOURCE not found!${NC}"
  exit 1
fi

# Создание структуры
if [[ "$CONFIG_PATH" == .* ]] && [[ "$CONFIG_PATH" != *.* ]]; then
  # Скрытый файл в home (например .zshrc)
  mkdir -p "$DEST"
  DEST="$DEST/$CONFIG_PATH"
else
  # Файл/папка в подпапке (например .config/kitty)
  mkdir -p "$(dirname "$DEST/$CONFIG_PATH")"
  DEST="$DEST/$CONFIG_PATH"
fi

# Копирование
cp -r "$SOURCE" "$DEST"
echo -e "${GREEN}✓${NC} Copied to $DEST"

# Бэкап оригинала
BACKUP="$SOURCE.backup-$(date +%Y%m%d-%H%M%S)"
mv "$SOURCE" "$BACKUP"
echo -e "${GREEN}✓${NC} Backed up original to $BACKUP"

# Stow
cd "$DOTFILES" || exit
if stow "$PACKAGE" 2>/dev/null; then
  echo -e "${GREEN}✓${NC} Stowed $PACKAGE"
else
  echo -e "${RED}✗${NC} Failed to stow (check conflicts)"
  exit 1
fi

# Проверка симлинка
if [ -L "$SOURCE" ]; then
  echo -e "${GREEN}✅ Success!${NC} $SOURCE is now managed by dotfiles\n"

  echo -e "${BLUE}Next steps:${NC}"
  echo "  cd ~/dotfiles"
  echo "  git add $PACKAGE/"
  echo "  git commit -m 'feat($PACKAGE): add configuration'"
  echo "  git push"
else
  echo -e "${RED}❌ Failed${NC} to create symlink"
  exit 1
fi
