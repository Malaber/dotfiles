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

# ssh (keychain)
eval $(keychain --eval --quiet id_rsa privat)

#path
export PATH=$PATH:$M2_HOME/bin:~/php

#standart editor
export EDITOR=vim

source ~/.aliases

