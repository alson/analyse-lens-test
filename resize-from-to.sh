#!/bin/bash

# Usage: ./resize-from-to.sh <source_path> <source_mag> <target_mag>
# Example: ./resize-from-to.sh ./images 1_2 2.5_1

set -e

src_path="$1"
src_mag="$2"
tgt_mag="$3"

# Parse magnifications
src_ratio=$(echo "$src_mag" | awk -F_ '{print $1/$2}')
tgt_ratio=$(echo "$tgt_mag" | awk -F_ '{print $1/$2}')
# Calculate resize factor
resize_factor=$(echo "($tgt_ratio)/($src_ratio)" | bc -l)

# Interpolation choice — see header comment for rationale.
# Upsampling: Catrom (sharp cubic, small local overshoot, no long-range
# ringing) — chosen because JPEG file size is the downstream sharpness
# proxy and Lanczos's Gibbs ringing inflates file size with synthetic
# halos rather than real captured detail.
# Downsampling: Mitchell (smooth cubic, no aliasing).
interp="Catrom"
if (( $(echo "$resize_factor < 1" | bc -l) )); then
    interp="Mitchell"
fi

process_image() {
    img="$1"
    fname=$(basename "$img")
    # Get original dimensions
    read width height < <(gm identify -format "%w %h" "$img")
    # Calculate new dimensions
    new_width=$(printf "%.0f" $(echo "$width * $resize_factor" | bc -l))
    new_height=$(printf "%.0f" $(echo "$height * $resize_factor" | bc -l))

    # --- Rough crop before upsampling ---
    # Calculate target aspect ratio
    aspect_ratio=$(echo "$width / $height" | bc -l)
    tgt_aspect_ratio=$(echo "$new_width / $new_height" | bc -l)
    # For rough crop, crop to the target aspect ratio, centered
    # Only if aspect ratios differ significantly (tolerance 0.01)
    crop_width="$width"
    crop_height="$height"
    if (( $(echo "($aspect_ratio > $tgt_aspect_ratio + 0.01)" | bc -l) )); then
        # Image is wider than target, crop width
        crop_width=$(printf "%.0f" $(echo "$height * $tgt_aspect_ratio" | bc -l))
    elif (( $(echo "($aspect_ratio + 0.01 < $tgt_aspect_ratio)" | bc -l) )); then
        # Image is taller than target, crop height
        crop_height=$(printf "%.0f" $(echo "$width / $tgt_aspect_ratio" | bc -l))
    fi
    # Perform rough crop (centered)
    gm convert "$img" -gravity center -crop "${crop_width}x${crop_height}+0+0" +repage "./resized_tmp/${fname}_roughcrop"

    # Resize image from rough crop
    gm convert "./resized_tmp/${fname}_roughcrop" -filter "$interp" -resize "${new_width}x${new_height}!" "./resized_tmp/$fname"

    # Crop or pad to original size, centered (precise)
    if [[ $new_width -ge $width && $new_height -ge $height ]]; then
        # Crop center
        gm convert "./resized_tmp/$fname" -gravity center -crop "${width}x${height}+0+0" +repage "./resized_tmp/${fname}_cropped"
    else
        # Pad center
        gm convert "./resized_tmp/$fname" -gravity center -background black -extent "${width}x${height}" "./resized_tmp/${fname}_cropped"
    fi

    # Output filename
    out_name="${fname%.*}|resized.jpg"
    mv "./resized_tmp/${fname}_cropped" "./$out_name"
}

mkdir -p ./resized_tmp

export resize_factor interp
export -f process_image
parallel -j 4 process_image ::: "$src_path"/*.jpg

rm -rf ./resized_tmp