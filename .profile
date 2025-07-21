#intelliJ
export IDEA_JDK=/usr/lib/jvm/intellij-jdk

#histcontrol (space before a command does not add it to command history)
export HISTCONTROL=ignorespace

# brew
eval $(/home/linuxbrew/.linuxbrew/bin/brew shellenv)

# #ruby
# eval "$(rbenv init -)"
# export PATH="$HOME/.rbenv/bin:$PATH"
# #PATH="$(ruby -r rubygems -e 'puts Gem.user_dir')/bin:$PATH"

#python
export PYENV_ROOT="$HOME/.pyenv"
command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init --path)"
eval "$(pyenv init -)"

#ansible
export PATH="$PATH:$HOME/ansible/venv/bin"

#conda (python)
#export PATH="$PATH:/opt/homebrew/anaconda3/bin"

# #node
# export NVM_DIR="$HOME/.nvm"
# [ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"  # This loads nvm
# [ -s "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm" ] && \. "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm"  # This loads nvm bash_completion
# export NODE_EXTRA_CA_CERTS="$HOME/etc_ssl_and_puki.pem"

# # gpg
# export GPG_TTY=$(tty)

# ssh
# Auto-detect or start ssh-agent
socket=$(find /tmp/ssh-* -type s -name "*agent*" 2>/dev/null | head -n1)
pid=$(ps aux | grep "[s]sh-agent" | head -n1 | awk '{print $2}')

if [ -n "$socket" ] && [ -n "$pid" ]; then
  export SSH_AUTH_SOCK="$socket"
  export SSH_AGENT_PID="$pid"
  echo "Reusing existing ssh-agent (pid $pid)"
else
  eval "$(ssh-agent -s)"
  echo "Started new ssh-agent"
fi

# Reusable function to add only missing SSH keys
function ssh-add-all {
    local key
    for key in ~/.ssh/id_ed25519; do
        if ! ssh-add -l | grep -q "$(ssh-keygen -lf "$key" | awk '{print $2}')"; then
            ssh-add "$key"
        fi
    done
}
ssh-add-all || true # add keys on initial .profile load, ignore failure

#zsh
unsetopt share_history

#standart editor
export EDITOR=vim

#kubectl krew
PATH="${PATH}:${HOME}/.krew/bin"

#kubectl config
export KUBECONFIG="${HOME}/.kube/config"

# podman compose
export COMPOSE_MENU=0

source ~/.aliases
source ~/.topsecretfbiundercover
