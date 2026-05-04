#!/bin/sh
ls -d [A-Z]* | while read lens; do (
    echo "Processing lens: $lens"
    cd "$lens"
    ls -d F*| while read aperture; do (
        echo "Processing aperture: $aperture"
        cd "$aperture"
        ~/projects/personal/fotografie/analyse-lens-test/make-9-crops.sh
        ~/projects/personal/fotografie/analyse-lens-test/select-crops.sh
    ); done
); done
