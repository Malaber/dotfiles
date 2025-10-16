#!/bin/bash
SCRIPTPATH=$(readlink -f "$0")
#echo $SCRIPTPATH
BASEDIR=$(dirname "$SCRIPTPATH")
#echo $BASEDIR

ln -sf $BASEDIR/.bashrc ~/
ln -sf $BASEDIR/.profile ~/
ln -sf $BASEDIR/.aliases ~/
ln -sf $BASEDIR/.tmux.conf.local ~/
ln -sf $BASEDIR/.zshrc ~/
ln -sf $BASEDIR ~/.dotfiles

git config --global core.excludesfile "$BASEDIR/.global_gitignore"
git config --global user.useConfigOnly true
git config --global alias.pushall '!git remote | xargs -L1 git push'
git config --global alias.oldest-ancestor '!bash -c '\''diff --old-line-format='' --new-line-format='' <(git rev-list --first-parent "${1:-master}") <(git rev-list --first-parent "${2:-HEAD}") | head -1'\'' -' # https://stackoverflow.com/a/4991675/10559526
git config --global push.autoSetupRemote true
git config --global alias.pushfwl "push --force-with-lease"

THEMES_FOLDER="$HOME/.oh-my-zsh/custom/themes"
mkdir -p $THEMES_FOLDER
ln -sf $BASEDIR/dschaedler.zsh-theme $THEMES_FOLDER/dschaedler.zsh-theme

echo -e "\nAPPLY" >> $BASEDIR/LastRun
date >> $BASEDIR/LastRun
