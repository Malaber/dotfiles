#!/bin/bash
SCRIPTPATH=$(readlink -f "$0")
#echo $SCRIPTPATH
BASEDIR=$(dirname "$SCRIPTPATH")
#echo $BASEDIR

ln -sf $BASEDIR/.profile ~/
ln -sf $BASEDIR/.aliases ~/

sudo pacman -S --needed $(cat $BASEDIR/packages_slim)
