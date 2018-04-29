#maven
export M2_HOME=/opt/maven

#intelliJ
export IDEA_JDK=/usr/lib/jvm/intellij-jdk


#ruby
export GEM_HOME=$HOME/.gem/ruby/2.4.0

#ssh
export SSH_ASKPASS="/usr/bin/ksshaskpass"
export SSH_AUTH_SOCK="${XDG_RUNTIME_DIR}/ssh-agent.socket"

#standart editor
export EDITOR=vim

#git
alias git='LANG=en_GB git'

#update script
alias update='pacaur -Syu && /home/dschaedler/custom_clientinfocollector.sh'

#hotelkette
alias hotelkette='/home/dschaedler/Hotelkette.sh'










#path
export PATH=$PATH:$HOME/.gem/ruby/2.4.0/bin:$M2_HOME/bin
