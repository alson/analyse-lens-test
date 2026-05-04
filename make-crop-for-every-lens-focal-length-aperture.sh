#!/bin/sh
ls -d [A-Z]* | while read lens; do (
    echo "Processing lens: $lens"
    cd "$lens"
    ls | while read focal_length; do (
        echo "Processing focal length: $focal_length"
        cd "$focal_length"
        ls -d F*| while read aperture; do (
            echo "Processing aperture: $aperture"
            cd "$aperture"
            if [ "$focal_length" = "35.0 mm" ]; then
                ~/projects/personal/fotografie/analyse-lens-test/make-crops-mixed-with-DX.sh
            else
                ~/projects/personal/fotografie/analyse-lens-test/make-crops.sh
            fi
            ~/projects/personal/fotografie/analyse-lens-test/select-crops.sh
        ); done
    ); done
); done
