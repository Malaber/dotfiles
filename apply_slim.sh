#!/bin/bash
SCRIPTPATH=$(readlink -f "$0")
#echo $SCRIPTPATH
BASEDIR=$(dirname "$SCRIPTPATH")
#echo $BASEDIR

ln -sf $BASEDIR/.bashrc ~/
ln -sf $BASEDIR/.aliases ~/.profile

sudo pacman -S --needed $(cat $BASEDIR/packages_slim)
