#!/bin/zsh

ls *.jpg | while read fn; do
    parts=(${(@s:|:)fn})
    lens="${parts[2]}"
    focal_length="${parts[3]}"
    aperture="${parts[4]}"
    mkdir -p "$lens/$focal_length/$aperture"
    mv -n "$fn" "$lens/$focal_length/$aperture/"
done