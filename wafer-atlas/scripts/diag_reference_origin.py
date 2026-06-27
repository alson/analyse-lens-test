"""Task #1: reconstruct where each wafer-atlas 'LSF reference shot' came from.
For each sweep's tile-sharpness per-shot CSV, find the centre-tile focus argmax
for lsf_mtf50, maze_fft_amp, and filesize, and compare to the hardcoded
lsf_ref_shot in task15. Reveals whether the references are true LSF focus picks
or (mislabeled) JPEG-filesize argmax.
"""
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness")

SWEEPS = [
    ("sweep1_M0.385", ROOT/"out_task2/per_shot_per_tile.csv", "100-400", 137),
    ("sweep2_M1.0",   ROOT/"out_apertures_for_calibration/per_shot_per_tile.csv",
     "200mm_f_4D_IF-ED__1_1__F11", 41),
    ("sweep3_M2.0",   ROOT/"out_task4/per_shot_per_tile.csv", "TC-2001", 47),
]


def argmax(recs, col):
    best = None
    for r in recs:
        try:
            v = float(r[col])
        except (ValueError, KeyError):
            continue
        if v <= 0:
            continue
        si = int(r["shot_idx"])
        if best is None or v > best[1]:
            best = (si, v)
    return best and best[0]


for name, csvpath, key, hardcoded in SWEEPS:
    if not csvpath.exists():
        print(f"{name}: CSV missing {csvpath}"); continue
    rows = []
    with open(csvpath) as f:
        for r in csv.DictReader(f):
            if key in r["sweep"]:
                rows.append(r)
    by_tile = defaultdict(list)
    for r in rows:
        by_tile[(r["tile_ix"], r["tile_iy"])].append(r)
    centre = by_tile.get(("0", "0")) or next(iter(by_tile.values()), [])
    a_lsf = argmax(centre, "lsf_mtf50_cy_per_px")
    a_maze = argmax(centre, "maze_fft_amp")
    a_fs = argmax(centre, "filesize_bytes")
    print(f"\n{name}: hardcoded ref={hardcoded}   (CSV {csvpath.parent.name}, "
          f"{len(rows)} rows, {len(by_tile)} tiles)")
    print(f"   centre tile (0,0):  lsf_mtf50 argmax={a_lsf}   "
          f"maze_fft argmax={a_maze}   filesize argmax={a_fs}")
    match = []
    if a_lsf == hardcoded: match.append("lsf")
    if a_maze == hardcoded: match.append("maze")
    if a_fs == hardcoded: match.append("filesize")
    print(f"   -> hardcoded {hardcoded} matches: {match or 'NONE'}")
