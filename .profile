#maven
export M2_HOME=/opt/maven

#intelliJ
export IDEA_JDK=/usr/lib/jvm/intellij-jdk

#ruby
export GEM_HOME=$HOME/.rbenv/versions/2.5.3
eval "$(rbenv init -)"
#PATH="$(ruby -r rubygems -e 'puts Gem.user_dir')/bin:$PATH"

#python
eval "$(pyenv init -)"

#ssh
unset SSH_AGENT_PID
if [ "${gnupg_SSH_AUTH_SOCK_by:-0}" -ne $$ ]; then
	  export SSH_AUTH_SOCK="$(gpgconf --list-dirs agent-ssh-socket)"
fi
export GPG_TTY=$(tty)
gpg-connect-agent updatestartuptty /bye >/dev/null
export SSH_ASKPASS='/usr/bin/ksshaskpass'
# Look at https://wiki.archlinux.org/index.php/KDE_Wallet#Using_the_KDE_Wallet_to_store_ssh_key_passphrases

#path
export PATH=$PATH:$M2_HOME/bin:~/php

#standart editor
export EDITOR=vim

source ~/.aliases
