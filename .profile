#intelliJ
export IDEA_JDK=/usr/lib/jvm/intellij-jdk

#coreutils mac
PATH="$(brew --prefix)/opt/coreutils/libexec/gnubin:$PATH"

#histcontrol (space before a command does not add it to command history)
export HISTCONTROL=ignorespace

#ruby
eval "$(rbenv init -)"
export PATH="$HOME/.rbenv/bin:$PATH"
#PATH="$(ruby -r rubygems -e 'puts Gem.user_dir')/bin:$PATH"

#python
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init --path)"
eval "$(pyenv init -)"
export REQUESTS_CA_BUNDLE="$HOME/etc_ssl_and_puki.pem"
# tkinter
export PATH="$PATH:/usr/local/opt/tcl-tk/bin"
export LDFLAGS="-L$(brew --prefix tcl-tk)/lib"
export CPPFLAGS="-I$(brew --prefix tcl-tk)/include"
export PKG_CONFIG_PATH="$(brew --prefix tcl-tk)/lib/pkgconfig"

#ansible
export PATH="$PATH:$HOME/ansible/venv/bin"

#conda (python)
#export PATH="$PATH:/opt/homebrew/anaconda3/bin"

#node
export NVM_DIR="$HOME/.nvm"
[ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"  # This loads nvm
[ -s "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm" ] && \. "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm"  # This loads nvm bash_completion
export NODE_EXTRA_CA_CERTS="$HOME/etc_ssl_and_puki.pem"

# gpg
export GPG_TTY=$(tty)

# ssh

## reusable function to add all ssh keys (used in osum and standalone)
function ssh-add-all {
    ssh-add --apple-use-keychain ~/.ssh/privat
    ssh-add --apple-use-keychain ~/.ssh/id_ed25519
}
ssh-add-all # add keys on initial .profile load

## osum
# you need to add a password named "OSUM" in your macOS keychain
function osum {
    $HOME/osum_plus/bin/ekca-ssh-init dschaedler
    ssh-add-all
}


#path
export PATH=$PATH:$M2_HOME/bin:~/php:~/.local/bin

#zsh
unsetopt share_history

#standart editor
export EDITOR=vim

#kubectl krew
PATH="${PATH}:${HOME}/.krew/bin"

#kubectl config
export KUBECONFIG="${HOME}/.kube/config"

# cookiecutter template
export LOCAL_DOCKER_BUILD_UID=$(id -u)
export LOCAL_DOCKER_BUILD_GID=$(id -g)
# can be removed once unused:
export DOCKER_COMPOSE_UID=$LOCAL_DOCKER_BUILD_UID
export DOCKER_COMPOSE_GID=$LOCAL_DOCKER_BUILD_GID
# end of removable portion
export LOCAL_DOCKER_BUILD_PLATFORM="linux/arm64"

# docker compose
export COMPOSE_MENU=0

# cns debugger
export CNS_DJANGO_DEBUGGER=pycharm

#maven
export M2_HOME=/opt/maven

# java
#export JAVA_HOME=`/usr/libexec/java_home -v 1.8`
export JAVA_HOME=/opt/homebrew/opt/openjdk@11
export PATH="$PATH:$JAVA_HOME/bin"

source ~/.aliases
source ~/.topsecretfbiundercover
