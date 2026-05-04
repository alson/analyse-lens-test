#!/bin/zsh

ls|while read fn; do 
    parts=(${(@s:|:)fn})
    dir="${parts[2]}/${parts[4]}/"
    mkdir -p "${dir}"
    mv "$fn" "${dir}"
done