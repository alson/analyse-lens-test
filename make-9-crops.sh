#!/bin/zsh
# Lossless 9-crop split (centre, four edges, four corners) of every
# *.jpg in the current directory. Outputs land under ./cropped/<pos>/.
#
# Replaces the previous gm-mogrify-with-re-encoding pipeline; the
# heavy lifting is now in resize-bulk/lossless_crops.py, which uses
# TurboJPEG.crop_multiple for true lossless JPEG transforms. Crop
# origins come from lens_test_detect_core.mcu so this script and the
# runtime cropper share a single source of truth.

set -e
SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR/resize-bulk"
uv run --project . python lossless_crops.py --mode full --source "$OLDPWD" --out "$OLDPWD/cropped" "$@"
