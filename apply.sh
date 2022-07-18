#!/bin/bash
SCRIPTPATH=$(readlink -f "$0")
#echo $SCRIPTPATH
BASEDIR=$(dirname "$SCRIPTPATH")
#echo $BASEDIR

sudo pacman -S --needed $(cat $BASEDIR/packages_slim)
yay -S --needed $(cat $BASEDIR/packages)

ln -sf $BASEDIR/.bashrc ~/
ln -sf $BASEDIR/.profile ~/
ln -sf $BASEDIR/.aliases ~/
ln -sf $BASEDIR/.tmux.conf.local ~/
ln -sf $BASEDIR/.zshrc ~/
ln -sf $BASEDIR/.config/plasma-workspace/env/askpass.sh ~/.config/plasma-workspace/env/askpass.sh

git config --global core.excludesfile "$BASEDIR/.global_gitignore"
git config --global user.useConfigOnly true
git config --global alias.pushall '!git remote | xargs -L1 git push'
git config --global alias.oldest-ancestor '!bash -c '\''diff --old-line-format='' --new-line-format='' <(git rev-list --first-parent "${1:-master}") <(git rev-list --first-parent "${2:-HEAD}") | head -1'\'' -' # https://stackoverflow.com/a/4991675/10559526

sudo cp -f $BASEDIR/dschaedler.zsh-theme /usr/share/oh-my-zsh/themes/dschaedler.zsh-theme

echo -e "\nAPPLY\n" >> $BASEDIR/LastRun
date >> $BASEDIR/LastRun
