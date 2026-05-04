#!/bin/zsh
#find [A-Z]* -mindepth 1 -type d | while read dn; do echo $(ls -S "$dn/"*.jpg | head -n1); done >! picks.txt

mkdir -p cropped/center cropped/left-edge cropped/right-edge cropped/top-edge cropped/bottom-edge cropped/top-left cropped/top-right cropped/bottom-right cropped/bottom-left

# Image dimensions
image_width=$(gm identify -format "%w\n" *.jpg | head -n 1)
image_height=$(gm identify -format "%h\n" *.jpg | head -n 1)

# Crop dimensions
crop_width=500
crop_height=500
center_x=$((image_width / 2 - (crop_width / 2)))
center_y=$((image_height / 2 - (crop_height / 2)))
left_edge_x=0
left_edge_y=$((image_height / 2 - (crop_height / 2)))
top_left_x=0
top_left_y=0
top_edge_x=$((image_width / 2 - (crop_width / 2)))
top_edge_y=0
top_right_x=$((image_width - crop_width))
top_right_y=0
right_edge_x=$((image_width - crop_width))
right_edge_y=$((image_height / 2 - (crop_height / 2)))
bottom_right_x=$((image_width - crop_width))
bottom_right_y=$((image_height - crop_height))
bottom_edge_x=$((image_width / 2 - (crop_width / 2)))
bottom_edge_y=$((image_height - crop_height))
bottom_left_x=0
bottom_left_y=$((image_height - crop_height))

# Run all crop positions in parallel using GNU parallel
parallel -j 9 --line-buffer '
    position={}
    case $position in
        center) x='$center_x'; y='$center_y' ;;
        left-edge) x='$left_edge_x'; y='$left_edge_y' ;;
        right-edge) x='$right_edge_x'; y='$right_edge_y' ;;
        top-edge) x='$top_edge_x'; y='$top_edge_y' ;;
        bottom-edge) x='$bottom_edge_x'; y='$bottom_edge_y' ;;
        top-left) x='$top_left_x'; y='$top_left_y' ;;
        top-right) x='$top_right_x'; y='$top_right_y' ;;
        bottom-right) x='$bottom_right_x'; y='$bottom_right_y' ;;
        bottom-left) x='$bottom_left_x'; y='$bottom_left_y' ;;
    esac
    echo "Making $position crops"
    gm mogrify -output-directory cropped/$position -crop '$crop_width'x'$crop_height'+$x+$y *.jpg
' ::: center left-edge right-edge top-edge bottom-edge top-left top-right bottom-right bottom-left
