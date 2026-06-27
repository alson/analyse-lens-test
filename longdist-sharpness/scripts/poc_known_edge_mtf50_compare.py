"""Compare ``mtf50_known_edge`` (CV-discovered edges) against the
auto-detect ``mtf50_slanted_edge`` from ``poc_longdist_algorithms.py``.

For each wide-angle dataset:
- NaN rate: ratio of NaN measurements per algorithm.
- Replicate spread (CV / range_pct): how stable the metric is across
  replicates of the same config.
- Ranking agreement vs ``radial_cutoff``: Spearman correlation of
  per-(lens, FL, aperture) sharpness order.

Output:
- A summary markdown table at
  ``poc_known_edge_mtf50_out/comparison_summary.md``.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).parent
KE_BASE = ROOT / "poc_known_edge_mtf50_out"
ALG_BASE = ROOT / "poc_longdist_algorithms_out"

DATASETS = [
    "wide2026_01_24",
    "wide2026_01_26",
    "wide2026_02_07",
    "wide2025_09_10",
    "mid2025_09_11",
]


def cv(s: pd.Series) -> float:
    s = s.dropna()
    if len(s) < 2:
        return float("nan")
    return float(s.std() / s.mean())


def summarise_one(key: str) -> dict:
    ke_csv = KE_BASE / key / "per_measurement.csv"
    alg_csv = ALG_BASE / key / "per_measurement.csv"
    out = {"dataset": key}

    # Known-edge algorithm (new)
    if ke_csv.exists():
        ke = pd.read_csv(ke_csv)
        t = ke[ke.role == "test"]
        out["ke_rows"] = len(t)
        out["ke_nan_rate"] = float(t.mtf50.isna().mean())
        cv_by = t.groupby(
            ["lens_dir", "focal_mm", "aperture_f", "edge_id"]
        )["mtf50"].agg(cv)
        out["ke_cv_median"] = float(cv_by.median())
        out["ke_cv_mean"] = float(cv_by.mean())
        out["ke_median_mtf50"] = float(t.mtf50.median())
    else:
        out["ke_rows"] = 0

    # Auto-detect algorithm (existing) — already aggregated per
    # (config, position) so we compare on the equivalent "fraction of
    # configs with a non-NaN measurement" by counting against
    # radial_cutoff (which always produces a value).
    if alg_csv.exists():
        alg = pd.read_csv(alg_csv)
        radial = alg[alg.algorithm == "radial_cutoff"]
        mtf = alg[alg.algorithm == "mtf50_slanted_edge"]
        # Auto-detect NaN rate at the (config, position) level
        n_possible = len(radial)
        n_actual = len(mtf)
        out["auto_nan_rate"] = 1.0 - n_actual / max(n_possible, 1)
        out["auto_range_pct_mean"] = float(mtf.range_pct.mean()) if len(mtf) else float("nan")
        out["auto_median_mtf50"] = float(mtf.top.median()) if len(mtf) else float("nan")

        # Ranking agreement: per (lens, FL, aperture), get the
        # auto-detect mtf50 (median over positions) and compare against
        # radial_cutoff median over positions. Then do same for
        # known-edge median over edges. Spearman ρ vs radial.
        radial_by = radial.groupby(
            ["lens_dir", "focal_mm", "aperture"]
        )["top"].median().rename("radial")
        auto_by = mtf.groupby(
            ["lens_dir", "focal_mm", "aperture"]
        )["top"].median().rename("auto")
        if ke_csv.exists():
            ke_test = ke[ke.role == "test"]
            ke_by = ke_test.groupby(
                ["lens_dir", "focal_mm", "aperture"]
            )["mtf50"].median().rename("ke")
        else:
            ke_by = pd.Series(dtype=float, name="ke")

        joined = pd.concat([radial_by, auto_by, ke_by], axis=1).dropna()
        if len(joined) >= 5:
            r_auto, _ = spearmanr(joined.radial, joined.auto)
            r_ke, _ = spearmanr(joined.radial, joined.ke)
            out["spearman_auto_vs_radial"] = float(r_auto)
            out["spearman_ke_vs_radial"] = float(r_ke)
            out["compared_configs"] = int(len(joined))

    return out


def main() -> int:
    rows = [summarise_one(k) for k in DATASETS]
    df = pd.DataFrame(rows)
    out_md = KE_BASE / "comparison_summary.md"
    KE_BASE.mkdir(exist_ok=True)
    with out_md.open("w") as f:
        f.write("# `mtf50_known_edge` vs `mtf50_slanted_edge` (auto-detect) comparison\n\n")
        f.write("Per-dataset summary of the §5.1 known-edge MTF50 follow-up.\n\n")
        f.write("- `*_nan_rate`: fraction of attempted measurements that returned NaN.\n")
        f.write("- `ke_cv_median`: median coefficient of variation across replicates per\n")
        f.write("  (lens, FL, aperture, edge). Lower = more stable.\n")
        f.write("- `auto_range_pct_mean`: mean (max-min)/median × 100 across replicates.\n")
        f.write("  Approximately 2×CV for n=3 replicates.\n")
        f.write("- `spearman_*_vs_radial`: ranking agreement with `radial_cutoff` over\n")
        f.write("  (lens, FL, aperture). Higher = the new metric ranks lenses similarly.\n\n")
        cols = [
            "dataset", "ke_rows", "ke_nan_rate", "auto_nan_rate",
            "ke_cv_median", "ke_cv_mean", "auto_range_pct_mean",
            "ke_median_mtf50", "auto_median_mtf50",
            "spearman_ke_vs_radial", "spearman_auto_vs_radial",
            "compared_configs",
        ]
        sub = df[cols].round(3).fillna("")
        f.write("| " + " | ".join(cols) + " |\n")
        f.write("| " + " | ".join(["---"] * len(cols)) + " |\n")
        for _, row in sub.iterrows():
            f.write("| " + " | ".join(str(v) for v in row.values) + " |\n")
    print(f"wrote {out_md}")
    print(df[["dataset", "ke_nan_rate", "auto_nan_rate", "ke_cv_median",
              "auto_range_pct_mean", "spearman_ke_vs_radial",
              "spearman_auto_vs_radial"]].round(3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
