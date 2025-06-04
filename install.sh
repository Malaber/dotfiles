#!/bin/bash
SCRIPTPATH=$(readlink -f "$0")
#echo $SCRIPTPATH
BASEDIR=$(dirname "$SCRIPTPATH")
#echo $BASEDIR

sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

UNDERCOVER_FILE="$HOME/.topsecretfbiundercover"
touch $UNDERCOVER_FILE
chmod 600 $UNDERCOVER_FILE

echo -e "\nINSTALL" >> $BASEDIR/LastRun
date >> $BASEDIR/LastRun
./apply.sh
