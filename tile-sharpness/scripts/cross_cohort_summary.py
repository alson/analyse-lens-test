"""Aggregate cross-cohort summary across the three 1:1 / cross-config runs.

Reads each cohort's ``peaks.csv``, computes per-(method, lens) mean
rank across all on-target tile positions, and prints a tidy comparison
table for each cohort. For the multi-copy 55mm cohort it also reports
per-method coefficient of variation across copies (sanity check: same
lens model should score similarly across samples).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(
    0,
    "/home/alson/shared/projects/personal/fotografie/"
    "analyse-lens-test/tile-sharpness/src",
)
sys.path.insert(
    0,
    "/home/alson/shared/projects/personal/fotografie/lens-test-detect-core/src",
)

from tile_sharpness.compare import cross_lens  # noqa: E402
from tile_sharpness.methods import METHODS  # noqa: E402


def _orient_sign(m: str) -> int:
    return 1 if METHODS[m].orientation == "higher_is_sharper" else -1


def cohort_table(peaks_csv: Path, label: str) -> pd.DataFrame:
    peaks = pd.read_csv(peaks_csv)
    per_tile = cross_lens(peaks)["per_tile"]
    summary = (
        per_tile.groupby(["method", "lens"])["rank"]
        .agg(["mean", "median", "count"])
        .round(2)
        .reset_index()
    )
    summary["cohort"] = label
    return summary


def coeff_var_per_method(peaks_csv: Path) -> pd.DataFrame:
    """For the multi-copy cohort, std/mean of per-(tile, method) peak across copies.

    Larger CV = more variability across "identical" lens copies. Methods
    with low CV are calibration-stable; high CV may flag scoring noise
    (or genuine sample-to-sample lens variation).
    """
    peaks = pd.read_csv(peaks_csv)
    peaks = peaks[peaks["on_target"]]
    rows = []
    for method in peaks["method"].unique():
        sub = peaks[peaks["method"] == method]
        # Apply orientation so all comparisons are "higher = sharper".
        sub = sub.assign(peak_o=sub["peak_value"] * _orient_sign(method))
        # CV across copies per (ix, iy, lens_family)
        sub["lens_family"] = sub["lens"].str.replace(r"\s+\d+$", "", regex=True)
        by_tile_fam = (
            sub.groupby(["lens_family", "ix", "iy"])["peak_o"]
            .agg(["mean", "std", "count"])
            .reset_index()
        )
        by_tile_fam = by_tile_fam[by_tile_fam["count"] >= 2]
        if by_tile_fam.empty:
            continue
        by_tile_fam["cv"] = (by_tile_fam["std"] / by_tile_fam["mean"]).abs()
        rows.append({
            "method": method,
            "median_cv": float(by_tile_fam["cv"].median()),
            "mean_cv": float(by_tile_fam["cv"].mean()),
            "n_tile_groups": int(len(by_tile_fam)),
        })
    return pd.DataFrame(rows).sort_values("median_cv")


def main() -> int:
    base = Path(
        "/home/alson/shared/projects/personal/fotografie/"
        "analyse-lens-test/tile-sharpness"
    )
    cohorts = {
        "bare_1to1": base / "out_bare1to1/peaks.csv",
        "resized_1to1": base / "out_resized1to1/peaks.csv",
        "multi_copy_55mm": base / "out_55mm/peaks.csv",
    }
    out_dir = base / "cross_cohort_summary"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_summaries = []
    for label, csv in cohorts.items():
        if not csv.exists():
            print(f"[skip] {label}: {csv} missing")
            continue
        s = cohort_table(csv, label)
        all_summaries.append(s)
        wide = s.pivot_table(
            index="lens", columns="method", values="mean"
        ).round(2)
        print(f"\n=== {label} — mean rank per (method × lens) ===")
        print(wide.to_string())
        wide.to_csv(out_dir / f"{label}_rank.csv")

    if cohorts["multi_copy_55mm"].exists():
        cv = coeff_var_per_method(cohorts["multi_copy_55mm"])
        print("\n=== multi_copy_55mm — coefficient of variation across copies ===")
        print(cv.to_string(index=False))
        cv.to_csv(out_dir / "multi_copy_55mm_cv.csv", index=False)

    if all_summaries:
        combined = pd.concat(all_summaries, ignore_index=True)
        combined.to_csv(out_dir / "all_cohort_summaries.csv", index=False)
        print(f"\n[done] outputs -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
