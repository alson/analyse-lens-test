"""Compute the delta between an originally-applied rename plan and a
corrected rename plan.

For each row that exists in both plans, if the new_path differs, emit
a delta-row whose source is the **applied** new_path (i.e. the current
on-disk location) and whose destination is the corrected new_path.

This is what you run when you've already executed the original plan
and now want to re-snap to a corrected version (e.g. after folding
in additional bellows corrections that change a few half-stop snaps).

For rows present only in the corrected plan, emit them as-is (they
need to be applied fresh).

The output is a normal rename plan CSV that `apply_rename_plan.py`
can consume.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def load_plan(p: Path) -> dict[str, dict]:
    if not p.exists():
        return {}
    rows = {}
    with p.open() as fh:
        for r in csv.DictReader(fh):
            rows[r["original_path"]] = r
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--original-plan", type=Path, required=True,
                   help="The plan that was already applied (orig -> applied_new).")
    p.add_argument("--corrected-plan", type=Path, required=True,
                   help="The plan with updated multipliers (orig -> corrected_new).")
    p.add_argument("--out", type=Path, required=True,
                   help="Output delta plan CSV.")
    args = p.parse_args(argv)

    orig = load_plan(args.original_plan)
    corr = load_plan(args.corrected_plan)

    delta_rows = []
    for orig_path, c_row in corr.items():
        applied = orig.get(orig_path)
        c_new = c_row["new_path"]
        if applied is None:
            # New row only in corrected plan — apply fresh
            row = dict(c_row)
            row["note"] = (row.get("note", "") + " (new in corrected)").strip()
            delta_rows.append(row)
            continue
        a_new = applied["new_path"]
        if a_new == c_new:
            # No change needed for this row
            continue
        # Source is now at the APPLIED new path; rename to CORRECTED new path
        row = dict(c_row)
        row["original_path"] = a_new
        # Replace the F-dir name in new_path with the corrected one — already
        # is c_new. Also rewrite new_F_dir from corrected plan.
        row["note"] = f"delta from previously-applied {applied['new_F_dir']}"
        delta_rows.append(row)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        if not delta_rows:
            print("No delta rows — corrected plan matches the applied plan.")
            # Still write an empty CSV with header for downstream tools
            w = csv.writer(fh)
            w.writerow(["original_path", "lens", "focal_mm", "tube_mm",
                        "reported_f", "bellows_multiplier", "effective_f",
                        "new_F_dir", "new_path", "note"])
            return 0
        fieldnames = list(delta_rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in delta_rows:
            w.writerow(r)
    print(f"Wrote {len(delta_rows)} delta rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
