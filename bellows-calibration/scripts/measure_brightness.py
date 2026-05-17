"""Measure center brightness for every JPG in a directory, pulling
EXIF metadata and computing linear-light luminance at several centre-
crop sizes. Designed for the 2026-05-17 bellows-factor validation
shoot on the Nikon Z7 (and works for any similar shot).

Output: a per-shot CSV with one row per JPG.

Columns include:
- filename, datetime, lens, focal_mm, fnum, exposure_time, iso,
  focus_distance_m, fec_dial, flash_mode
- y_lin_center_<N>  for N in [100, 200, 400, 800, 1600] px

Usage:
    python measure_brightness.py --dir <dir> --out <csv>
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

CROPS_PX = [100, 200, 400, 800, 1600]

EXIF_FIELDS = [
    "FileName", "DateTimeOriginal",
    "FocalLength", "FNumber", "ExposureTime", "ISO",
    "FocusDistance",
    "LensModel", "Model",
    "Flash", "FlashCompensation",
    "ExternalFlashStatus", "FlashControlMode",
]


def srgb_to_linear(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float64) / 255.0
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def y_center(p: Path, crop_px: int) -> float:
    img = np.asarray(Image.open(p).convert("RGB"))
    h, w, _ = img.shape
    half = crop_px // 2
    sl = img[h//2 - half: h//2 + half, w//2 - half: w//2 + half]
    lin = srgb_to_linear(sl)
    y = 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]
    return float(np.mean(y))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", type=Path, required=True,
                   help="Directory containing .JPG files")
    p.add_argument("--out", type=Path, required=True,
                   help="Output CSV path")
    p.add_argument("--pattern", default="*.JPG",
                   help="Glob pattern (default *.JPG)")
    args = p.parse_args(argv)

    files = sorted(args.dir.glob(args.pattern))
    if not files:
        print(f"No files matching {args.pattern} in {args.dir}", file=sys.stderr)
        return 1

    # Pull EXIF for all files in one shot
    cmd = ["exiftool", "-T", "-q"] + [f"-{f}" for f in EXIF_FIELDS] + [str(f) for f in files]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        w = csv.writer(fh)
        header = list(EXIF_FIELDS) + [f"y_lin_center_{n}" for n in CROPS_PX]
        w.writerow(header)
        for line, path in zip(out.strip().splitlines(), files):
            parts = line.split("\t")
            if len(parts) < len(EXIF_FIELDS):
                parts += [""] * (len(EXIF_FIELDS) - len(parts))
            ys = [y_center(path, n) for n in CROPS_PX]
            w.writerow(parts + [f"{y:.6f}" for y in ys])
            print(f"  {path.name}  Y@400px = {ys[2]:.4f}", file=sys.stderr)
    print(f"Wrote {len(files)} rows to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
