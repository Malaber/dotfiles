source $(brew --prefix)/share/antigen/antigen.zsh

# Load the oh-my-zsh's library.
antigen use oh-my-zsh

# Load bundles from external repos
antigen bundles <<EOBUNDLES
    zsh-users/zsh-autosuggestions
    zsh-users/zsh-syntax-highlighting
    zsh-users/zsh-completions
    git
EOBUNDLES

antigen theme dschaedler

# 3. Commit Antigen Configuration
antigen apply

source ~/.profile
