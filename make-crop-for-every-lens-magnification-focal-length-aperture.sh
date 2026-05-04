#!/bin/sh
ls -d [A-Z]* | while read lens; do (
    echo "Processing lens: $lens"
    cd "$lens"
    ls | while read magnification; do (
        echo "Processing magnification: $magnification"
        cd "$magnification"
        ls | while read focal_length; do (
            echo "Processing focal length: $focal_length"
            cd "$focal_length"
            ls -d F*| while read aperture; do (
                echo "Processing aperture: $aperture"
                cd "$aperture"
                # ~/projects/personal/fotografie/analyse-lens-test/make-9-crops.sh
                ~/projects/personal/fotografie/analyse-lens-test/make-17-crops.sh
                ~/projects/personal/fotografie/analyse-lens-test/select-crops.sh
                SRC_FOLDER="$PWD"
                mkdir -p ../../../1_1-resized/"$focal_length/$aperture"
                cd ../../../1_1-resized/"$focal_length/$aperture"
                echo "Resizing to 1:1 for $lens $magnification $focal_length $aperture"
                ~/projects/personal/fotografie/analyse-lens-test/resize-from-to.sh "$SRC_FOLDER" $magnification 1_1
                ~/projects/personal/fotografie/analyse-lens-test/make-17-crops.sh
                ~/projects/personal/fotografie/analyse-lens-test/select-crops.sh
                mkdir -p ../../../2_1-resized/"$focal_length/$aperture"
                cd ../../../2_1-resized/"$focal_length/$aperture"
                echo "Resizing to 2:1 for $lens $magnification $focal_length $aperture"
                ~/projects/personal/fotografie/analyse-lens-test/resize-from-to.sh "$SRC_FOLDER" $magnification 2_1
                ~/projects/personal/fotografie/analyse-lens-test/make-17-crops.sh
                ~/projects/personal/fotografie/analyse-lens-test/select-crops.sh
            ); done
        ); done
    ); done
); done
