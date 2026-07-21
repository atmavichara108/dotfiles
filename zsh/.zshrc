# Enable Powerlevel10k instant prompt. Should stay close to the top of ~/.zshrc.
# Initialization code that may require console input (password prompts, [y/n]
# confirmations, etc.) must go above this block; everything else may go below.
# Suppress instant prompt warning (direnv console output conflict)
typeset -g POWERLEVEL9K_INSTANT_PROMPT=quiet
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

# If you come from bash you might have to change your $PATH.
export PATH=$HOME/bin:$HOME/.local/bin:/usr/local/bin:$PATH

# Path to your Oh My Zsh installation.
export ZSH="$HOME/.oh-my-zsh"

# Set name of the theme to load --- if set to "random", it will
# load a random theme each time Oh My Zsh is loaded, in which case,
# to know which specific one was loaded, run: echo $RANDOM_THEME
# See https://github.com/ohmyzsh/ohmyzsh/wiki/Themes
ZSH_THEME="powerlevel10k/powerlevel10k"

# Set list of themes to pick from when loading at random
# Setting this variable when ZSH_THEME=random will cause zsh to load
# a theme from this variable instead of looking in $ZSH/themes/
# If set to an empty array, this variable will have no effect.
# ZSH_THEME_RANDOM_CANDIDATES=( "robbyrussell" "agnoster" )

# Uncomment the following line to use case-sensitive completion.
# CASE_SENSITIVE="true"

# Uncomment the following line to use hyphen-insensitive completion.
# Case-sensitive completion must be off. _ and - will be interchangeable.
# HYPHEN_INSENSITIVE="true"

# Uncomment one of the following lines to change the auto-update behavior
# zstyle ':omz:update' mode disabled  # disable automatic updates
# zstyle ':omz:update' mode auto      # update automatically without asking
# zstyle ':omz:update' mode reminder  # just remind me to update when it's time

# Uncomment the following line to change how often to auto-update (in days).
# zstyle ':omz:update' frequency 13

# Uncomment the following line if pasting URLs and other text is messed up.
# DISABLE_MAGIC_FUNCTIONS="true"

# Uncomment the following line to disable colors in ls.
# DISABLE_LS_COLORS="true"

# Uncomment the following line to disable auto-setting terminal title.
# DISABLE_AUTO_TITLE="true"

# Uncomment the following line to enable command auto-correction.
# ENABLE_CORRECTION="true"

# Uncomment the following line to display red dots whilst waiting for completion.
# You can also set it to another string to have that shown instead of the default red dots.
# e.g. COMPLETION_WAITING_DOTS="%F{yellow}waiting...%f"
# Caution: this setting can cause issues with multiline prompts in zsh < 5.7.1 (see #5765)
# COMPLETION_WAITING_DOTS="true"

# Uncomment the following line if you want to disable marking untracked files
# under VCS as dirty. This makes repository status check for large repositories
# much, much faster.
# DISABLE_UNTRACKED_FILES_DIRTY="true"

# Uncomment the following line if you want to change the command execution time
# stamp shown in the history command output.
# You can set one of the optional three formats:
# "mm/dd/yyyy"|"dd.mm.yyyy"|"yyyy-mm-dd"
# or set a custom format using the strftime function format specifications,
# see 'man strftime' for details.
# HIST_STAMPS="mm/dd/yyyy"

# Would you like to use another custom folder than $ZSH/custom?
# ZSH_CUSTOM=/path/to/new-custom-folder

# Which plugins would you like to load?
# Standard plugins can be found in $ZSH/plugins/
# Custom plugins may be added to $ZSH_CUSTOM/plugins/
# Example format: plugins=(rails git textmate ruby lighthouse)
# Add wisely, as too many plugins slow down shell startup.
plugins=(git zsh-autosuggestions z zsh-syntax-highlighting)

source $ZSH/oh-my-zsh.sh

# User configuration

# export MANPATH="/usr/local/man:$MANPATH"

# You may need to manually set your language environment
# export LANG=en_US.UTF-8

# Preferred editor for local and remote sessions
# if [[ -n $SSH_CONNECTION ]]; then
#   export EDITOR='vim'
# else
#   export EDITOR='nvim'
# fi

# Compilation flags
# export ARCHFLAGS="-arch $(uname -m)"

# Set personal aliases, overriding those provided by Oh My Zsh libs,
# plugins, and themes. Aliases can be placed here, though Oh My Zsh
# users are encouraged to define aliases within a top-level file in
# the $ZSH_CUSTOM folder, with .zsh extension. Examples:
# - $ZSH_CUSTOM/aliases.zsh
# - $ZSH_CUSTOM/macos.zsh
# For a full list of active aliases, run `alias`.
#
# Example aliases
# alias zshconfig="mate ~/.zshrc"
# alias ohmyzsh="mate ~/.oh-my-zsh"
alias sp="sudo pacman"
alias sv="sudo vim"
alias ls="ls -lah"
alias n='nvim'
alias ld='cd ~/dotfiles/ && lazygit'
alias nqc='n ~/dotfiles/qtile/.config/qtile/config.py'
alias s='source ~/.zshrc'
alias nz='nvim ~/.zshrc'
alias tt='taskwarrior-tui'
alias sq='cd ~/dotfiles/ && stow -R qtile'
alias termx="ssh -p 8022 '192.168.0.24'"
alias termxm="ssh -p 8022 '10.192.172.83'"
alias ccb="xclip -sel c"
alias to-dv="ssh -i /home/rudra/.ssh/id_ed25519 -p 28108 'dv@re-search.wiki'"
alias to-serp="ssh root@167.235.252.4"
alias opc="opencode"

export PATH="$HOME/bin:$PATH"
export PATH=$PATH:~/go/bin
# To customize prompt, run `p10k configure` or edit ~/.p10k.zsh.
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh

# FZF setup
# Источники для keybindings и completion
source /usr/share/fzf/key-bindings.zsh
source /usr/share/fzf/completion.zsh

# Базовые настройки fzf
export FZF_DEFAULT_OPTS="
--height 60%
--layout=reverse
--border
--info=inline
--prompt=' '
--pointer=''
--marker=''
--color=fg:#c0caf5,bg:#1a1b26,hl:#ff9e64
--color=fg+:#c0caf5,bg+:#292e42,hl+:#ff9e64
--color=info:#7aa2f7,prompt:#7dcfff,pointer:#7dcfff
--color=marker:#9ece6a,spinner:#9ece6a,header:#9ece6a
"

# Использовать fd вместо find (быстрее и умнее)
export FZF_DEFAULT_COMMAND='fd --type f --hidden --follow --exclude .git'
export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
export FZF_ALT_C_COMMAND='fd --type d --hidden --follow --exclude .git'

# Preview для CTRL-T с bat
export FZF_CTRL_T_OPTS="
--preview 'bat --style=numbers --color=always --line-range :500 {}'
--preview-window right:60%:wrap
"

# Preview для ALT-C с tree или eza
export FZF_ALT_C_OPTS="
--preview 'eza --tree --level=2 --color=always {} | head -200'
--preview-window right:50%
"

# Preview для CTRL-R (история команд)
export FZF_CTRL_R_OPTS="
--preview 'echo {}'
--preview-window down:3:wrap
"

# Продвинутые функции и алиасы
# Открыть файл в vim через fzf
alias vf='vim $(fzf --preview "bat --color=always {}")'

# Поиск по содержимому файлов с ripgrep
alias rgf='rg --line-number --no-heading --color=always --smart-case . | fzf --ansi --delimiter : --preview "bat --color=always {1} --highlight-line {2}" --preview-window "+{2}/2"'

# Найти и перейти в директорию
alias cdf='cd $(fd --type d | fzf --preview "eza --tree --level=2 {}")'

# Убить процесс через fzf
alias fkill='ps -ef | fzf | awk "{print \$2}" | xargs kill -9'

# Git-интеграция: checkout ветки
alias gcof='git branch | fzf | xargs git checkout'

# Git log с preview
alias glf='git log --oneline --color=always | fzf --ansi --preview "git show --color=always {1}" --preview-window right:60%'

# Найти и открыть PDF
alias pf='fd -e pdf | fzf --preview "pdftotext {} - | head -100"'

# fzf для git
_fzf_complete_git() {
  _fzf_complete --prompt="git> " -- "$@" < <(
    git --help -a | grep -E '^\s+' | awk '{print $1}'
  )
}

# Git checkout с preview веток
fco() {
  local branches branch
  branches=$(git branch -a) &&
  branch=$(echo "$branches" | fzf --preview 'git log --oneline --color=always {1}') &&
  git checkout $(echo "$branch" | sed "s/.* //" | sed "s#remotes/[^/]*/##")
}

# Git commit browser
fshow() {
  git log --graph --color=always \
      --format="%C(auto)%h%d %s %C(black)%C(bold)%cr" "$@" |
  fzf --ansi --no-sort --reverse --tiebreak=index --bind=ctrl-s:toggle-sort \
      --bind "ctrl-m:execute:
                (grep -o '[a-f0-9]\{7\}' | head -1 |
                xargs -I % sh -c 'git show --color=always % | less -R') << 'FZF-EOF'
                {}
FZF-EOF"
}
export EDITOR=nvim

# TMUX
#
# if [ -z "$TMUX" ]; then
#   tmux start-server            # пустой сервер, Continuum подцепит снапшот
#   tmux attach || tmux new -s main
#   exit
# fi
#
# TheFuck
eval $(thefuck --alias)

# CUDA
export PATH=/usr/local/cuda-11.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-11.8/lib64:$LD_LIBRARY_PATH
export CUDA_PATH=/usr/local/cuda-11.8

# Navi — interactive cheatsheet (Ctrl+G)
eval "$(navi widget zsh)"

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion

# bun completions
[ -s "/home/rudra/.bun/_bun" ] && source "/home/rudra/.bun/_bun"

# bun
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"

# direnv
eval "$(direnv hook zsh)"

# === Proxy: Happ primary (SOCKS5h 10808 / HTTP 10809), Tor 9050 fallback ===
export ALL_PROXY="socks5h://127.0.0.1:10808"
export all_proxy="$ALL_PROXY"
export http_proxy="http://127.0.0.1:10809"
export https_proxy="http://127.0.0.1:10809"
export HTTP_PROXY="$http_proxy"
export HTTPS_PROXY="$https_proxy"
export NO_PROXY="localhost,127.0.0.1,::1,.local"
export TOR_PROXY="socks5://127.0.0.1:9050"
