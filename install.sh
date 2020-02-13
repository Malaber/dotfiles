#!/bin/bash

yay -S zsh oh-my-zsh-git

cd
git clone https://github.com/gpakosz/.tmux.git
ln -s -f .tmux/.tmux.conf
cp .tmux/.tmux.conf.local .

echo  "Read https://bbs.archlinux.org/viewtopic.php?id=127894 to disable compression and speed up package building"

sudo chsh -s /bin/zsh $USER

./dotfiles/apply.sh
