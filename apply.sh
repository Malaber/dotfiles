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
sudo cp -f $BASEDIR/dschaedler.zsh-theme /usr/share/oh-my-zsh/themes/dschaedler.zsh-theme

git config --global alias.pushall '!git remote | xargs -L1 git push --all'

date >> $BASEDIR/LastRun
