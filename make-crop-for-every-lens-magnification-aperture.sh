#!/bin/sh
ls -d [A-Z]* | while read lens; do (
    echo "Processing lens: $lens"
    cd "$lens"
    ls | while read magnification; do (
        echo "Processing magnification: $magnification"
        cd "$magnification"
            ls -d F*| while read aperture; do (
                echo "Processing aperture: $aperture"
                cd "$aperture"
                # ~/projects/personal/fotografie/analyse-lens-test/make-9-crops.sh
                ~/projects/personal/fotografie/analyse-lens-test/make-17-crops.sh
                ~/projects/personal/fotografie/analyse-lens-test/select-crops.sh
                SRC_FOLDER="$PWD"
                mkdir -p ../../../1_1-resized/"$aperture"
                mkdir -p ../../../2_1-resized/"$aperture"
                cd ../../../1_1-resized/"$aperture"
                ~/projects/personal/fotografie/analyse-lens-test/resize-from-to.sh $SRC_FOLDER $magnification 1_1
                ~/projects/personal/fotografie/analyse-lens-test/make-17-crops.sh
                ~/projects/personal/fotografie/analyse-lens-test/select-crops.sh
                cd ../../2_1-resized/"$aperture"
                ~/projects/personal/fotografie/analyse-lens-test/resize-from-to.sh $SRC_FOLDER $magnification 2_1
                ~/projects/personal/fotografie/analyse-lens-test/make-17-crops.sh
                ~/projects/personal/fotografie/analyse-lens-test/select-crops.sh
            ); done
    ); done
); done
