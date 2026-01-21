#!/bin/bash

UNDERCOVER_FILE="$HOME/.topsecretfbiundercover"
touch $UNDERCOVER_FILE
chmod 600 $UNDERCOVER_FILE

git config --global core.excludesfile "$HOME/.global_gitignore"
git config --global user.useConfigOnly true
git config --global alias.pushall '!git remote | xargs -L1 git push'
git config --global alias.oldest-ancestor '!bash -c '\''diff --old-line-format='' --new-line-format='' <(git rev-list --first-parent "${1:-master}") <(git rev-list --first-parent "${2:-HEAD}") | head -1'\'' -' # https://stackoverflow.com/a/4991675/10559526
git config --global push.autoSetupRemote true
git config --global alias.pushfwl "push --force-with-lease"
git config --global gpg.format "ssh"

# force lf everywhere
git config --global core.autocrlf false
git config --global core.eol lf
