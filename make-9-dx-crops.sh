#!/bin/zsh
# Lossless 8-crop split of the DX (APS-C inner) sub-region of every
# *.jpg in the current directory. Outputs land under ./cropped/dx-*/.
#
# Note: the historical script of this name produced 9 full-frame crops
# (despite the "dx" in the name) at hard-coded coordinates and a fixed
# 500x500 size. It is replaced here with the actual DX-only behaviour
# the name implies. Use make-17-crops.sh to get full+DX together.

set -e
SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR/resize-bulk"
uv run --project . python lossless_crops.py --mode dx --source "$OLDPWD" --out "$OLDPWD/cropped" "$@"
