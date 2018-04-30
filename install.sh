#!/bin/bash

pacaur -S zsh oh-my-zsh-git

cd
git clone https://github.com/gpakosz/.tmux.git
ln -s -f .tmux/.tmux.conf
cp .tmux/.tmux.conf.local .
