"""Walk an existing test-raw-data tree, identify each F-dir's
(lens, focal, tube) configuration, look up the bellows multiplier
from per_config.csv, and output a rename plan CSV that maps each
original F-dir to its effective-aperture-name equivalent.

For 2026-02-18 the tree layout is:
    <slug>/<mag>[/<focal mm>]/F<n>/...
For 2026-05-13 the tree layout is:
    <slug>/f_<n>/...   (lowercase, no <focal> subdir yet)

Slug names like "NIKKOR Z MC 105mm f_2.8 S + 26mm extension"
parse to: base lens + tube length (the user's "+26mm" labels
correspond to the total stack length, e.g. 10+16=26).

Diopter additions ("+ Canon 500D", "+ Nikon 5T") add no bellows
contribution beyond what the extension tube itself adds; they're
included in the slug name but only the tube part affects the
multiplier.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import subprocess
from pathlib import Path

LENS_ALIASES = {
    "NIKKOR Z MC 105mm f_2.8 S": "MC 105",
    "NIKKOR Z MC 105mm f_2.8 VR S": "MC 105",
    "NIKKOR Z 24-120mm f_4 S": "24-120",
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S": "100-400",
    "Viltrox 85mm f_2 EVO": "Viltrox 85",
    "Viltrox AF 85mm f_2.0 Z": "Viltrox 85",
}

TUBE_RE = re.compile(r"\+ (\d+)mm extension")
DIOPTER_TAGS = (
    "+ Canon 500D", "+ Nikon 5T", "+ Nikon 6T", "+ Olympus MCON-35",
    "+ Raynox M-150", "+ Raynox M-250",
)

HALF_STOPS = [
    1.4, 1.6, 1.8, 2.0, 2.2, 2.5, 2.8, 3.2, 3.5, 4.0, 4.5, 5.0,
    5.6, 6.3, 7.1, 8.0, 9.0, 10, 11, 13, 14, 16, 18, 20, 22, 25,
    29, 32, 36, 40, 45, 51, 57, 64,
]


def snap(f: float) -> str:
    h = min(HALF_STOPS, key=lambda x: abs(math.log2(x / f)))
    return f"{h:g}"


TC_TAGS = (
    "Z TC-1.4x", "Z TC-2.0x", "+ TC-1401", "+ TC-2001",
    "+ Kenko Pro 300 DG 1.4x", "+ Kenko Pro 300 DG 2x",
)


def parse_slug(slug: str) -> tuple[str | None, int]:
    """Return (lens_short, tube_mm). tube_mm is 0 for bare-lens slugs
    (including those with diopters or teleconverters, neither of
    which adds bellows). Returns (None, 0) if no lens recognised."""
    tube_m = TUBE_RE.search(slug)
    tube_mm = int(tube_m.group(1)) if tube_m else 0
    base = slug
    if tube_m:
        base = slug[:tube_m.start()].rstrip()
    for tag in DIOPTER_TAGS + TC_TAGS:
        if tag in base:
            base = base.replace(tag, "").strip()
            while base.endswith("+") or base.endswith(" "):
                base = base[:-1].strip()
    for full, short in LENS_ALIASES.items():
        if base.startswith(full):
            return short, tube_mm
    return None, tube_mm


F_DIR_RE = re.compile(r"^[Ff]?[_]?(\d+(?:\.\d+|_\d+)?)$")
FOCAL_DIR_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*mm$")


def parse_f_dir(name: str) -> float | None:
    # Handle "F4", "F5.6", "f_4", "f_5_6"
    m = re.match(r"^[Ff]_?(\d+(?:_\d+)?(?:\.\d+)?)$", name)
    if not m:
        return None
    s = m.group(1).replace("_", ".")
    try:
        return float(s)
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--calibration", type=Path, required=True,
                   help="per_config.csv from build_calibration.py")
    p.add_argument("--tree", type=Path, required=True,
                   help="Root of a date-stamped tree, e.g. ~/.../test-raw-data/2026-05-13")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)

    # Index calibration by (lens, focal_mm, tube_mm). Both bare-MFD
    # (tube=0) and tube>0 rows are indexed; tube=-1 (bare-INF reference)
    # rows are skipped because their multiplier is 1.0 by definition.
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

    # Walk tree for F-dirs
    rows = []
    for path in args.tree.rglob("[Ff]*"):
        if not path.is_dir():
            continue
        name = path.name
        if name == "cropped" or name.startswith("cropped"):
            continue
        f_reported = parse_f_dir(name)
        if f_reported is None:
            continue
        # Skip empty cruft dirs (no real files at any depth)
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
        # Figure out the focal length: either from a "120.0 mm" subdir, or
        # from the slug if it's a prime, or pick the most-common test focal.
        focal_mm = None
        for part in parts[1:]:
            mfocal = FOCAL_DIR_RE.match(part)
            if mfocal:
                focal_mm = float(mfocal.group(1))
                break
        if focal_mm is None:
            # No focal subdir (e.g. 2026-05-13 layout). Peek at EXIF of any
            # JPG in this F-dir to discover the actual focal length.
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
                # Fall back to cal table — picks lowest focal, mostly OK for primes
                cand_focals = sorted({fm for (l, fm, tm) in cal if l == lens and tm == tube_mm})
                if not cand_focals:
                    continue
                focal_mm = cand_focals[0]
        key = (lens, focal_mm, tube_mm)
        m = cal.get(key)
        if m is None:
            # Try interpolation: same lens, same tube, nearest focal
            same_lens_tube = [k for k in cal if k[0] == lens and k[2] == tube_mm]
            if same_lens_tube:
                nearest = min(same_lens_tube, key=lambda k: abs(k[1] - focal_mm))
                m = cal[nearest]
                key = nearest
                interp_note = f"interp_from_{nearest[1]:g}mm"
            else:
                rows.append({
                    "original_path": str(rel),
                    "lens": lens, "focal_mm": focal_mm, "tube_mm": tube_mm,
                    "reported_f": f_reported,
                    "bellows_multiplier": "", "effective_f": "",
                    "new_F_dir": "", "new_path": "",
                    "note": "NO_CALIBRATION",
                })
                continue
        else:
            interp_note = ""
        eff = f_reported * m
        eff_snapped = snap(eff)
        new_F_dir = f"F{eff_snapped}"
        # Preserve case of original first letter
        if name[0] == "f":
            new_F_dir = new_F_dir.lower().replace("f", "f_", 1)
        new_path = rel.parent / new_F_dir
        rows.append({
            "original_path": str(rel),
            "lens": lens, "focal_mm": focal_mm, "tube_mm": tube_mm,
            "reported_f": f_reported,
            "bellows_multiplier": f"{m:.4f}",
            "effective_f": f"{eff:.2f}",
            "new_F_dir": new_F_dir,
            "new_path": str(new_path),
            "note": interp_note,
        })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "original_path", "lens", "focal_mm", "tube_mm", "reported_f",
            "bellows_multiplier", "effective_f", "new_F_dir", "new_path", "note",
        ])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["original_path"]))
    print(f"Wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
