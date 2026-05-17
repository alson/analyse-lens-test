"""Recompute a rename plan's new_path / new_F_dir / effective_f
using updated bellows multipliers from per_config.csv, while keeping
the existing plan's original_path / reported_f / lens / focal_mm
/ tube_mm rows.

This is the right tool when the source tree has ALREADY been renamed
according to an older plan, and you want to express what the plan
SHOULD have been with corrected multipliers. The output is a plan in
the same shape as the original; pair it with build_delta_plan.py to
produce the (already-applied) → (corrected) delta rename.
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

HALF_STOPS = [
    1.4, 1.6, 1.8, 2.0, 2.2, 2.5, 2.8, 3.2, 3.5, 4.0, 4.5, 5.0,
    5.6, 6.3, 7.1, 8.0, 9.0, 10, 11, 13, 14, 16, 18, 20, 22, 25,
    29, 32, 36, 40, 45, 51, 57, 64,
]


def snap(f: float) -> str:
    h = min(HALF_STOPS, key=lambda x: abs(math.log2(x / f)))
    return f"{h:g}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--original-plan", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True,
                   help="Corrected per_config.csv with updated bellows multipliers.")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)

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

    out_rows = []
    with args.original_plan.open() as fh:
        rdr = csv.DictReader(fh)
        fieldnames = rdr.fieldnames or []
        for r in rdr:
            try:
                lens = r["lens"]
                focal = float(r["focal_mm"])
                tube = int(r["tube_mm"])
                reported = float(r["reported_f"])
            except (KeyError, ValueError):
                out_rows.append(r)
                continue
            key = (lens, focal, tube)
            m = cal.get(key)
            if m is None:
                # Try interpolation: same lens, same tube, nearest focal
                same = [k for k in cal if k[0] == lens and k[2] == tube]
                if same:
                    nearest = min(same, key=lambda k: abs(k[1] - focal))
                    m = cal[nearest]
                    r["note"] = (r.get("note", "") + f" interp_from_{nearest[1]:g}mm").strip()
            if m is None:
                out_rows.append(r)
                continue
            eff = reported * m
            eff_snapped = snap(eff)
            orig_F_dir = Path(r["original_path"]).name
            # Determine case of original F-dir to mirror in new_F_dir
            if orig_F_dir.startswith("f"):
                new_F_dir = f"f_{eff_snapped}"
            else:
                new_F_dir = f"F{eff_snapped}"
            new_path = str(Path(r["original_path"]).parent / new_F_dir)
            r["bellows_multiplier"] = f"{m:.4f}"
            r["effective_f"] = f"{eff:.2f}"
            r["new_F_dir"] = new_F_dir
            r["new_path"] = new_path
            out_rows.append(r)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print(f"Wrote {len(out_rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
