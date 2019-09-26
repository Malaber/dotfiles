#maven
export M2_HOME=/opt/maven

#intelliJ
export IDEA_JDK=/usr/lib/jvm/intellij-jdk

#current stuff
alias cdpa="cd /home/dschaedler/Git/Github.com/Malaber/praxisarbeit-sem3"

#rm safety
alias rm="rm -I"

#vstuido code
alias codehere="code . &"

#ruby
export GEM_HOME=$HOME/.rbenv/versions/2.5.3
eval "$(rbenv init -)"
#PATH="$(ruby -r rubygems -e 'puts Gem.user_dir')/bin:$PATH"

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
alias sshconfig="$EDITOR ~/.ssh/config"

# bat
alias cat='bat --plain --paging never'

#standart editor
export EDITOR=vim

#update script
alias update='yay -Syu && /home/dschaedler/custom_clientinfocollector.sh'

#add DNS to resolve.conf
alias nameserverstuff='echo "nameserver 1.1.1.1\nnameserver 8.8.8.8" | sudo tee /etc/resolv.conf'

# reload .profile file
alias sourceprofile="source ~/.profile"

#docker-compose
alias dc="docker-compose"

#hotelkette
alias hotelkette='/home/dschaedler/Hotelkette.sh'

#ldapbrowser
alias ldapbrowser='javaws ~/Downloads/ldapbrowser/ldapbrowser\lbe.jar'

#jit
alias jit='javaws ~/Firma/intranet-tool.jnlp &'

#ps aux
alias psauxgrep='ps -aux | head -1 && ps -aux | grep'

#git
alias git='LANG=en_GB git'
alias gmff='git merge --ff-only'
alias gitconfiggithub='git config user.name "Malaber" && git config user.email "32635600+Malaber@users.noreply.github.com"'
alias gpa='git pushall'
gitrebasi() {
    git rebase -i HEAD~"$1" --autostash
}
alias grba='git rebase --autostash'

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
export PATH=$PATH:$M2_HOME/bin:~/php
