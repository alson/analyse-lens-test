#!/bin/sh
# Post-process the three cohort runs: compute compare + crop exports.
# Run from the tile-sharpness project root after the analyse runs finish.

set -eu

for cohort in out_bare1to1 out_resized1to1 out_55mm; do
    if [ ! -f "$cohort/peaks.csv" ]; then
        echo "[skip] $cohort/peaks.csv missing" >&2
        continue
    fi
    echo "=== compare: $cohort ==="
    uv run --no-progress tile-sharpness compare "$cohort/peaks.csv"
    echo "=== cross-lens-crops: $cohort (centre + 4 mid-edges) ==="
    uv run --no-progress tile-sharpness cross-lens-crops "$cohort/peaks.csv" \
        --out "$cohort/cross_lens_crops" \
        --tile 0,0 --tile -3,0 --tile 3,0 --tile 0,-2 --tile 0,2
done

echo "=== cross-cohort summary ==="
uv run --no-progress python scripts/cross_cohort_summary.py
