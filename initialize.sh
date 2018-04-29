#!/bin/bash
SCRIPTPATH=$(readlink -f "$0")
#echo $SCRIPTPATH
BASEDIR=$(dirname "$SCRIPTPATH")
#echo $BASEDIR


ln -s $BASEDIR/.profile ~/
ln -s $BASEDIR/.tmux.conf.local ~/
ln -s $BASEDIR/.zshrc ~/


date >> $BASEDIR/LastRun
