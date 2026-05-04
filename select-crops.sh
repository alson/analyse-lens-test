#!/bin/sh
ls cropped | while read d; do (
    cd cropped/$d
    cp "$(ls -S *.jpg | head -n1)" pick.jpg
); done
