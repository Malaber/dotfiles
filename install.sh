#!/bin/bash

yay -S --needed zsh oh-my-zsh-git

cd
git clone https://github.com/gpakosz/.tmux.git
ln -s -f .tmux/.tmux.conf
cp .tmux/.tmux.conf.local .

echo  "Read https://bbs.archlinux.org/viewtopic.php?id=127894 to disable compression and speed up package building"

sudo chsh -s /bin/zsh $USER

echo "" >> ~/.topsecretfbiundercover
chmod 600 ~/.topsecretfbiundercover

echo -e "\nINSTALL" >> $BASEDIR/LastRun
./dotfiles/apply.sh
