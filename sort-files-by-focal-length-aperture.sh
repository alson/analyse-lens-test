#!/bin/sh

ls | while read lens; do
    echo Processing "$lens"
    (
        cd "$lens";
        if [ $(ls *.nef *.jpg | wc -l) -gt 0 ]; then
            ls | while read file; do
                focal_length_aperture=$(echo "$file" | cut -d\| -f3-5 | sed 's/^\(.*|\|\)\([0-9][0-9.]* mm|F[0-9][0-9.]*\)[^0-9]*$/\2/')
                focal_length=$(echo "$focal_length_aperture" | cut -d'|' -f1)
                mkdir -p "$focal_length"
                mv "$file" "$focal_length"
            done
        fi
        ls | while read focal_length; do
            (cd "$focal_length";
            if [ $(ls *.nef *.jpg | wc -l) -gt 0 ]; then
                ls | while read file; do
                    focal_length_aperture=$(echo "$file" | cut -d\| -f3-5 | sed 's/^\(.*|\|\)\([0-9][0-9.]* mm|F[0-9][0-9.]*\)[^0-9]*$/\2/')
                    aperture=$(echo "$focal_length_aperture" | cut -d'|' -f2)
                    mkdir -p "$aperture"
                    mv "$file" "$aperture/"
                done
            fi
            )
        done
    )
done