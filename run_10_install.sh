#!/bin/bash

brew bundle --file=/dev/stdin <<EOF
{{ range .packages.darwin.brews -}}
brew {{ . | quote }}
{{ end -}}
{{ range .packages.darwin.casks -}}
cask {{ . | quote }}
{{ end -}}
EOF

UNDERCOVER_FILE="$HOME/.topsecretfbiundercover"
touch $UNDERCOVER_FILE
chmod 600 $UNDERCOVER_FILE

# git
git config --global core.excludesfile "$HOME/.global_gitignore"
git config --global user.useConfigOnly true
git config --global push.autoSetupRemote true
git config --global gpg.format "ssh"

## force user config to be per repository
git config --global --unset user.name
git config --global --unset user.email
git config --global --unset user.signingkey

## force lf everywhere
git config --global core.autocrlf false
git config --global core.eol lf

## aliases
git config --global alias.pushall '!git remote | xargs -L1 git push'
git config --global alias.oldest-ancestor '!bash -c '\''diff --old-line-format='' --new-line-format='' <(git rev-list --first-parent "${1:-master}") <(git rev-list --first-parent "${2:-HEAD}") | head -1'\'' -' # https://stackoverflow.com/a/4991675/10559526
git config --global alias.pushfwl "push --force-with-lease"
