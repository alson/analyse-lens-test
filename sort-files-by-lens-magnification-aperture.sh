#!/bin/zsh

ls *.jpg | while read fn; do
    parts=(${(@s:|:)fn})
    lens="${parts[2]}"
    magnification="${parts[3]}"
    focal_length="${parts[4]}"
    aperture="${parts[5]}"
    mkdir -p "$lens/$magnification/$aperture"
    mv -n "$fn" "$lens/$magnification/$aperture/"
done