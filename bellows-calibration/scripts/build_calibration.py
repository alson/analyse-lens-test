"""Aggregate per-shot brightness into per-(lens, focal, tube)
configurations, compute bellows multiplier and effective f-number,
and write per_config.csv.

Reads:
  per_shot.csv            — output of measure_brightness.py
  tube_assignments.csv    — manual mapping of group-first-file → tube

Writes:
  per_config.csv          — one row per (lens, focal, tube), with the
                            bellows multiplier and effective-f for
                            each standard reported aperture.
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

# Standard half-stop scale to snap effective f-numbers onto
HALF_STOPS = [
    1.4, 1.6, 1.8, 2.0, 2.2, 2.5, 2.8, 3.2, 3.5, 4.0, 4.5, 5.0,
    5.6, 6.3, 7.1, 8.0, 9.0, 10, 11, 13, 14, 16, 18, 20, 22, 25,
    29, 32, 36, 40, 45, 51, 57, 64,
]

# Reported apertures to compute effective-f for each (lens, focal, tube).
# Covers the F-dir names seen across the 2026-01/02/05 test-raw-data trees.
REPORTED_F = [2.0, 2.8, 4.0, 4.5, 5.6, 8.0, 11.0, 16.0]


def snap_half_stop(f: float) -> float:
    return min(HALF_STOPS, key=lambda h: abs(math.log2(h / f)))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--per-shot", type=Path, required=True)
    p.add_argument("--tube-assignments", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--crop-col", default="y_lin_center_400",
                   help="Which brightness column to use as reference (default 400 px crop)")
    args = p.parse_args(argv)

    # Load per-shot data
    shots = []
    with args.per_shot.open() as fh:
        for r in csv.DictReader(fh):
            shots.append(r)

    # Build a dict: filename → row
    by_name = {r["FileName"]: r for r in shots}

    # Load tube assignments
    assignments = []
    with args.tube_assignments.open() as fh:
        for r in csv.DictReader(fh):
            # Skip comment-style "# ..." section lines (their first_file column
            # won't match a real DSC filename).
            if r["section"].startswith("#"):
                continue
            r["n_frames"] = int(r["n_frames"])
            r["focal_mm"] = float(r["focal_mm"])
            r["tube_mm"] = int(r["tube_mm"])
            assignments.append(r)

    # For each assignment, compute mean brightness over its n consecutive frames
    # starting at first_file (numerically in DSC sequence). The first_file may
    # be given with or without the .JPG extension.
    import re
    DSC_RE = re.compile(r"^(.+?)(\d{4})(\.[Jj][Pp][Gg])?$")

    def consecutive_files(first: str, n: int) -> list[str]:
        m = DSC_RE.match(first)
        if not m:
            raise ValueError(f"Can't parse DSC filename: {first!r}")
        prefix = m.group(1)
        start = int(m.group(2))
        ext = m.group(3) or ".JPG"
        files = []
        for i in range(n * 4):  # tolerate up to 3 missing frames
            cand = f"{prefix}{start+i:04d}{ext}"
            if cand in by_name:
                files.append(cand)
            if len(files) == n:
                break
        return files

    # Compute per-assignment mean Y
    for a in assignments:
        files = consecutive_files(a["first_file"], a["n_frames"])
        ys = [float(by_name[f][args.crop_col]) for f in files]
        a["mean_y"] = sum(ys) / len(ys)
        a["files"] = ";".join(files)

    # Group by (lens, focal) and find the bare-INF row (preferred) or
    # bare-MFD row (fallback) in each group. Using bare-INF as the
    # reference makes the multiplier an ABSOLUTE bellows ratio
    # (effective_f / reported_f at infinity), so it captures both the
    # lens's own hidden bellows at MFD AND the tube's contribution.
    by_lens_focal = defaultdict(list)
    for a in assignments:
        by_lens_focal[(a["lens"], a["focal_mm"])].append(a)

    rows_out = []
    for (lens, focal), group in by_lens_focal.items():
        bare_inf = [a for a in group if a["tube_mm"] == -1]
        bare_mfd = [a for a in group if a["tube_mm"] == 0]
        ref_rows = bare_inf if bare_inf else bare_mfd
        ref_kind = "bare_inf" if bare_inf else ("bare_mfd" if bare_mfd else "")
        if not ref_rows:
            for a in group:
                a["bellows"] = ""
                a["delta_ev"] = ""
                a["reference_kind"] = ""
                rows_out.append(a)
            continue
        mean_y_ref = sum(b["mean_y"] for b in ref_rows) / len(ref_rows)
        for a in group:
            if a["mean_y"] <= 0 or mean_y_ref <= 0:
                a["bellows"] = ""
                a["delta_ev"] = ""
            else:
                ratio = mean_y_ref / a["mean_y"]
                a["bellows"] = math.sqrt(ratio)
                a["delta_ev"] = math.log2(ratio)
            a["reference_kind"] = ref_kind
            rows_out.append(a)

    # Write per_config.csv
    args.out.parent.mkdir(parents=True, exist_ok=True)
    header = ["lens", "focal_mm", "tube_mm", "section", "first_file", "n_frames",
              "mean_y", "reference_kind", "delta_ev_vs_ref", "bellows_multiplier"]
    for f in REPORTED_F:
        header.append(f"effective_f_at_reported_F{f}")
        header.append(f"effective_f_at_reported_F{f}_snapped")
    with args.out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for a in rows_out:
            row = [a["lens"], a["focal_mm"], a["tube_mm"], a["section"],
                   a["first_file"], a["n_frames"],
                   f"{a['mean_y']:.6f}",
                   a.get("reference_kind", ""),
                   f"{a['delta_ev']:.3f}" if a["delta_ev"] != "" else "",
                   f"{a['bellows']:.4f}" if a["bellows"] != "" else ""]
            if a["bellows"] == "":
                row.extend([""] * (2 * len(REPORTED_F)))
            else:
                for f in REPORTED_F:
                    eff = f * a["bellows"]
                    row.append(f"{eff:.2f}")
                    row.append(f"{snap_half_stop(eff):g}")
            w.writerow(row)
    print(f"Wrote {len(rows_out)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
