#maven
export M2_HOME=/opt/maven

#intelliJ
export IDEA_JDK=/usr/lib/jvm/intellij-jdk


#ruby
export GEM_HOME=$HOME/.gem/ruby/2.4.0

#ssh
export SSH_ASKPASS="/usr/bin/ksshaskpass"
export SSH_AUTH_SOCK="${XDG_RUNTIME_DIR}/ssh-agent.socket"
alias sshaddauto="$HOME/.config/autostart-scripts/ssh-add.sh"
alias sshaddfirm='ssh-add ~/.ssh/id_rsa'
alias sshaddpriv='ssh-add ~/.ssh/privat'

#standart editor
export EDITOR=vim

#git
alias git='LANG=en_GB git'

#update script
alias update='pacaur -Syu && /home/dschaedler/custom_clientinfocollector.sh'

#hotelkette
alias hotelkette='/home/dschaedler/Hotelkette.sh'

#git
alias gmff='git merge --ff-only'

#docker 
alias dockerkillall='docker kill $(docker ps -q)'
alias dockerdeleteallstoppedcontainers='docker rm $(docker ps -a -q)'
alias dockerdeleteallimages='docker rmi $(docker images -q)'

#lastpass
alias lpscp='lpass show -G -c -p'
alias lpsp='lpass show -G -p'
alias lps='lpass show -G'

#make
alias remake='make realclean && make'

#path
export PATH=$PATH:$HOME/.gem/ruby/2.4.0/bin:$M2_HOME/bin
