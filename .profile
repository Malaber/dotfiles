#maven
export M2_HOME=/opt/maven

#intelliJ
export IDEA_JDK=/usr/lib/jvm/intellij-jdk

#coreutils mac
PATH="$(brew --prefix)/opt/coreutils/libexec/gnubin:$PATH"

#ruby
eval "$(rbenv init -)"
export PATH="$HOME/.rbenv/bin:$PATH"
#PATH="$(ruby -r rubygems -e 'puts Gem.user_dir')/bin:$PATH"

#python
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
eval "$(pyenv init --path)"
eval "$(pyenv init -)"

#node
# source /usr/share/nvm/init-nvm.sh
export NODE_EXTRA_CA_CERTS="/home/dschaedler/Firma/Zertifikate/npm_ca_bundle.pem"

# gpg
export GPG_TTY=$(tty)

#path
export PATH=$PATH:$M2_HOME/bin:~/php:~/.local/bin

#standart editor
export EDITOR=vim

#kubectl krew
PATH="${PATH}:${HOME}/.krew/bin"

#ONEpy
export ONEPY_DEBUGGER=pycharm

source ~/.aliases
source ~/.topsecretfbiundercover
