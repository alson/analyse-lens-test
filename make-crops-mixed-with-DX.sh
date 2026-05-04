#!/bin/zsh
mkdir -p cropped/center cropped/left-edge cropped/right-edge cropped/DX-left-edge cropped/DX-right-edge
image_width=$(gm identify -format "%w\n" *.jpg | head -n 1)
image_height=$(gm identify -format "%h\n" *.jpg | head -n 1)
if [ "$image_width" -le 6000 ]; then
    echo "Detected DX image dimensions: ${image_width}x${image_height}"
    is_dx=true
else
    echo "Detected FX image dimensions: ${image_width}x${image_height}"
    is_dx=false
fi
center_crop_with=500
center_crop_height=500
edge_crop_width=400
edge_crop_height=1000
center_x=$((image_width / 2 - (center_crop_with / 2)))
center_y=$((image_height / 2 - (center_crop_height / 2)))
left_edge_x=0
left_edge_y=$((image_height / 2 - (edge_crop_height / 2)))
right_edge_x=$((image_width - edge_crop_width))
right_edge_y=$((image_height / 2 - (edge_crop_height / 2)))
if [ "$is_dx" = true ]; then
    echo Making center crops
    ls *.jpg|while read fn; do gm convert -crop ${center_crop_with}x${center_crop_height}+${center_x}+${center_y} "$fn" cropped/center/"$(basename "$fn")";done     
    echo making DX left-edge crops
    ls *.jpg|while read fn; do gm convert -crop ${edge_crop_width}x${edge_crop_height}+${left_edge_x}+${left_edge_y} "$fn" cropped/DX-left-edge/"$(basename "$fn")";done     
    echo making DX right-edge crops
    ls *.jpg|while read fn; do gm convert -crop ${edge_crop_width}x${edge_crop_height}+${right_edge_x}+${right_edge_y} "$fn" cropped/DX-right-edge/"$(basename "$fn")";done     

else
    echo Making center crops
    ls *.jpg|while read fn; do gm convert -crop ${center_crop_with}x${center_crop_height}+${center_x}+${center_y} "$fn" cropped/center/"$(basename "$fn")";done     
    echo making left-edge crops
    ls *.jpg|while read fn; do gm convert -crop ${edge_crop_width}x${edge_crop_height}+${left_edge_x}+${left_edge_y} "$fn" cropped/left-edge/"$(basename "$fn")";done     
    echo making right-edge crops
    ls *.jpg|while read fn; do gm convert -crop ${edge_crop_width}x${edge_crop_height}+${right_edge_x}+${right_edge_y} "$fn" cropped/right-edge/"$(basename "$fn")";done     
    dx_image_width=5408
    dx_image_height=3600
    dx_x_margin=$(( (image_width - dx_image_width) / 2 ))
    dx_y_margin=$(( (image_height - dx_image_height) / 2 ))
    dx_left_edge_x=$dx_x_margin
    dx_left_edge_y=$(( dx_y_margin + (dx_image_height / 2) - (edge_crop_height / 2) ))
    dx_right_edge_x=$((dx_x_margin + dx_image_width - edge_crop_width))
    dx_right_edge_y=$dx_left_edge_y
    echo making DX left-edge crops
    ls *.jpg|while read fn; do gm convert -crop ${edge_crop_width}x${edge_crop_height}+${dx_left_edge_x}+${dx_left_edge_y} "$fn" cropped/DX-left-edge/"$(basename "$fn")";done     
    echo making DX right-edge crops
    ls *.jpg|while read fn; do gm convert -crop ${edge_crop_width}x${edge_crop_height}+${dx_right_edge_x}+${dx_right_edge_y} "$fn" cropped/DX-right-edge/"$(basename "$fn")";done     
fi
