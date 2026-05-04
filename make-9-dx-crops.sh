#!/bin/zsh
#find [A-Z]* -mindepth 1 -type d | while read dn; do echo $(ls -S "$dn/"*.jpg | head -n1); done >! picks.txt
mkdir -p cropped/center cropped/left-edge cropped/right-edge cropped/top-edge cropped/bottom-edge cropped/top-left cropped/top-right cropped/bottom-right cropped/bottom-left
echo Making center crops
ls *.jpg|while read fn; do gm convert -crop 500x500+2750+1750 "$fn" cropped/center/"$(basename "$fn")";done     
echo making left-edge crops
ls *.jpg|while read fn; do gm convert -crop 500x500+0+1750 "$fn" cropped/left-edge/"$(basename "$fn")";done
echo making right-edge crops
ls *.jpg|while read fn; do gm convert -crop 500x500+5500+1750 "$fn" cropped/right-edge/"$(basename "$fn")";done
echo making top-edge crops
ls *.jpg|while read fn; do gm convert -crop 500x500+2750+0 "$fn" cropped/top-edge/"$(basename "$fn")";done
echo making bottom-edge crops
ls *.jpg|while read fn; do gm convert -crop 500x500+2750+2500 "$fn" cropped/bottom-edge/"$(basename "$fn")";done
echo making top-left crops
ls *.jpg|while read fn; do gm convert -crop 500x500+0+0 "$fn" cropped/top-left/"$(basename "$fn")";done
echo making top-right crops
ls *.jpg|while read fn; do gm convert -crop 500x500+5500+0 "$fn" cropped/top-right/"$(basename "$fn")";done
echo making bottom-right crops
ls *.jpg|while read fn; do gm convert -crop 500x500+5500+2500 "$fn" cropped/bottom-right/"$(basename "$fn")";done
echo making bottom-left crops
ls *.jpg|while read fn; do gm convert -crop 500x500+0+2500 "$fn" cropped/bottom-left/"$(basename "$fn")";done
