#!/bin/zsh
mkdir -p cropped/center cropped/left-edge cropped/right-edge
echo Making center crops
ls *.jpg|while read fn; do gm convert -crop 500x500+3878+2502 "$fn" cropped/center/"$(basename "$fn")";done     
echo making left-edge crops
ls *.jpg|while read fn; do gm convert -crop 400x1000+0+2252 "$fn" cropped/left-edge/"$(basename "$fn")";done     
echo making right-edge crops
ls *.jpg|while read fn; do gm convert -crop 400x1000+7856+2252 "$fn" cropped/right-edge/"$(basename "$fn")";done     
