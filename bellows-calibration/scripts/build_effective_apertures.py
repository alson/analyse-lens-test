"""Generate per-tree `effective_apertures.csv` — the canonical
lookup table for downstream code that needs the EXACT (un-rounded)
effective f-number of every F-dir in a tree.

For each F-dir under the tree, this records:

- slug, mag (if present in path), focal_mm, tube_mm
- F_dir_name (current on-disk name, snapped to a standard half-stop)
- reported_f (parsed from the F-dir name interpreted as the lens's
  CPU-reported aperture, i.e. what's in EXIF; for renamed dirs this
  is the *original* pre-rename reported value, looked up via the
  rename manifest or recovered by inverse-multiplying)
- effective_f_exact (unrounded; e.g. f/5.86, f/10.67)
- bellows_multiplier (effective_f_exact / reported_f)
- bellows_delta_ev (2·log2(multiplier))

The exact value is what downstream calculations should use for
diffraction limits, step-size estimation, etc. The F-dir name is
just the snapped half-stop label.

Inputs:
  --calibration  per_config.csv  (bellows multipliers per lens/focal/tube)
  --tree         test-raw-data/<date>  (the tree to scan)
  --rename-plan  rename_plan_<date>.csv  (optional; for recovering
                 the original reported_f when the F-dir name has
                 been renamed)
  --out          tree/effective_apertures.csv

Idempotent — safe to re-run after additional renames.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import subprocess
from pathlib import Path

# Reuse the parsing helpers from build_rename_plan.py
import importlib.util
import sys
THIS_DIR = Path(__file__).parent
spec = importlib.util.spec_from_file_location(
    "build_rename_plan",
    THIS_DIR / "build_rename_plan.py",
)
brp = importlib.util.module_from_spec(spec)
sys.modules["build_rename_plan"] = brp
spec.loader.exec_module(brp)

parse_slug = brp.parse_slug
parse_f_dir = brp.parse_f_dir
FOCAL_DIR_RE = brp.FOCAL_DIR_RE


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--tree", type=Path, required=True)
    p.add_argument("--rename-plan", type=Path, default=None,
                   help="Optional rename plan CSV for recovering the original "
                        "reported_f if F-dir was renamed.")
    p.add_argument("--out", type=Path, default=None,
                   help="Output CSV path (default: <tree>/effective_apertures.csv)")
    args = p.parse_args(argv)

    out_csv = args.out or (args.tree / "effective_apertures.csv")

    # Index calibration by (lens, focal_mm, tube_mm)
    cal = {}
    with args.calibration.open() as fh:
        for r in csv.DictReader(fh):
            try:
                lens = r["lens"]
                focal = float(r["focal_mm"])
                tube = int(r["tube_mm"])
                m = float(r["bellows_multiplier"]) if r["bellows_multiplier"] else None
            except (KeyError, ValueError):
                continue
            if tube >= 0 and m is not None:
                cal[(lens, focal, tube)] = m

    # Index rename plan by new_path → original reported_f (so we can
    # recover the original aperture from a renamed F-dir)
    new_path_to_orig_f = {}
    if args.rename_plan and args.rename_plan.exists():
        with args.rename_plan.open() as fh:
            for r in csv.DictReader(fh):
                if r.get("new_path") and r.get("reported_f"):
                    new_path_to_orig_f[r["new_path"]] = float(r["reported_f"])

    rows = []
    for path in args.tree.rglob("[Ff]*"):
        if not path.is_dir():
            continue
        name = path.name
        if name == "cropped" or name.startswith("cropped"):
            continue
        if "bellows-rename-tmp" in name:
            continue
        if not any(p.is_file() for p in path.rglob("*")):
            continue
        rel = path.relative_to(args.tree)
        parts = rel.parts
        if len(parts) < 2:
            continue
        slug = parts[0]
        lens, tube_mm = parse_slug(slug)
        if not lens:
            continue
        # Focal length from "120.0 mm" subdir or EXIF
        focal_mm = None
        for part in parts[1:]:
            m = FOCAL_DIR_RE.match(part)
            if m:
                focal_mm = float(m.group(1))
                break
        if focal_mm is None:
            jpgs = list(path.glob("*.jpg")) + list(path.glob("*.JPG"))
            if jpgs:
                try:
                    out = subprocess.run(
                        ["exiftool", "-T", "-FocalLength", str(jpgs[0])],
                        capture_output=True, text=True, check=True,
                    ).stdout.strip()
                    focal_mm = float(out.split()[0])
                except (subprocess.CalledProcessError, IndexError, ValueError):
                    pass
            if focal_mm is None:
                cand = sorted({fm for (l, fm, tm) in cal if l == lens and tm == tube_mm})
                if not cand:
                    continue
                focal_mm = cand[0]

        # Calibration multiplier (use exact, not interpolated; if not
        # present, fall back to nearest focal for same lens+tube)
        key = (lens, focal_mm, tube_mm)
        m = cal.get(key)
        if m is None:
            same = [k for k in cal if k[0] == lens and k[2] == tube_mm]
            if same:
                nearest = min(same, key=lambda k: abs(k[1] - focal_mm))
                m = cal[nearest]
                key = nearest
        if m is None:
            continue

        # Original reported_f: try the rename plan first; fall back to
        # interpreting the current F-dir name (which is the original
        # if no rename happened, the snapped post-rename name otherwise)
        reported_f = new_path_to_orig_f.get(str(rel))
        if reported_f is None:
            reported_f = parse_f_dir(name)
        if reported_f is None:
            continue

        eff = reported_f * m
        delta_ev = 2.0 * math.log2(m)

        mag = ""
        for part in parts[1:]:
            if re.match(r"^\d+_\d+(\.\d+)?(-resized)?$", part):
                mag = part
                break

        rows.append({
            "slug": slug,
            "mag": mag,
            "focal_mm": focal_mm,
            "tube_mm": tube_mm,
            "F_dir_path": str(rel),
            "F_dir_name": name,
            "reported_f": reported_f,
            "effective_f_exact": eff,
            "bellows_multiplier": m,
            "bellows_delta_ev": delta_ev,
            "lens": lens,
        })

    args.out.parent.mkdir(parents=True, exist_ok=True) if args.out else None
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "slug", "lens", "mag", "focal_mm", "tube_mm",
            "F_dir_path", "F_dir_name",
            "reported_f", "effective_f_exact",
            "bellows_multiplier", "bellows_delta_ev",
        ])
        w.writeheader()
        for r in sorted(rows, key=lambda x: x["F_dir_path"]):
            w.writerow({
                "slug": r["slug"], "lens": r["lens"], "mag": r["mag"],
                "focal_mm": r["focal_mm"], "tube_mm": r["tube_mm"],
                "F_dir_path": r["F_dir_path"], "F_dir_name": r["F_dir_name"],
                "reported_f": f"{r['reported_f']:.2f}",
                "effective_f_exact": f"{r['effective_f_exact']:.4f}",
                "bellows_multiplier": f"{r['bellows_multiplier']:.4f}",
                "bellows_delta_ev": f"{r['bellows_delta_ev']:.3f}",
            })
    print(f"Wrote {len(rows)} rows to {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
