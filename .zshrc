# Load the oh-my-zsh configlibrary.
export ZSH=$HOME/.oh-my-zsh
ZSH_THEME="dschaedler"
plugins=(
    git
)

source $ZSH/oh-my-zsh.sh
source ~/.profile

test -e "${HOME}/.iterm2_shell_integration.zsh" && source "${HOME}/.iterm2_shell_integration.zsh" || true

