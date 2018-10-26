#maven
export M2_HOME=/opt/maven

#intelliJ
export IDEA_JDK=/usr/lib/jvm/intellij-jdk


#ruby
export GEM_HOME=$HOME/.gem/ruby/2.4.0

#ssh
unset SSH_AGENT_PID
if [ "${gnupg_SSH_AUTH_SOCK_by:-0}" -ne $$ ]; then
	  export SSH_AUTH_SOCK="$(gpgconf --list-dirs agent-ssh-socket)"
fi
export GPG_TTY=$(tty)
gpg-connect-agent updatestartuptty /bye >/dev/null

alias sshaddfirm='ssh-add ~/.ssh/id_rsa'
alias sshaddpriv='ssh-add ~/.ssh/privat'
alias sshaddauto='ssh-add ~/.ssh/id_rsa ~/.ssh/privat'

#standart editor
export EDITOR=vim

#git
alias git='LANG=en_GB git'

#update script
alias update='yay -Syu && /home/dschaedler/custom_clientinfocollector.sh'

#add DNS to resolve.conf
alias nameserverstuff='echo "nameserver 1.1.1.1\nnameserver 8.8.8.8" | sudo tee /etc/resolv.conf'

alias sourceprofile="source ~/.profile"

#docker-compose
alias dc="docker-compose"

#hotelkette
alias hotelkette='/home/dschaedler/Hotelkette.sh'

#ps aux
alias psauxgrep='ps -aux | head -1 && ps -aux | grep'
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
