"""Cross-sweep and within-sweep secondary aggregations.

These read a ``peaks.csv`` already produced by ``analyse`` and answer
two specific questions:

* **Cross-lens comparison.** Given a set of sweeps that all framed the
  same subject but used different lenses (e.g. four bare native
  macros all at 1:1), do the four methods agree on which lens is
  sharpest? Per-tile-position ranking of sweeps per method, plus a
  centre-tile summary and Spearman ρ across methods on the centre
  ranking.
* **Symmetric-corner asymmetry.** Within one sweep, pair tile
  positions ``(+ix, +iy)`` with ``(-ix, -iy)`` (and ``(+ix, -iy)``
  with ``(-ix, +iy)``). For a well-centred lens those pairs should
  have similar peak metric values; persistent asymmetry per method is
  a decentering signal.

Both outputs are CSVs intended for direct inspection / plotting.
``analyse`` does not call these — they're a follow-up step keyed off
``peaks.csv`` (cheap, deterministic).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .methods import METHODS


def _orient(method: str) -> int:
    """Sign multiplier: +1 if higher is sharper, -1 if lower is sharper."""
    return 1 if METHODS[method].orientation == "higher_is_sharper" else -1


def cross_lens(peaks: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Rank sweeps per (method, tile-position) on the peak metric.

    Returns two DataFrames:

    * ``per_tile``: one row per ``(method, ix, iy, sweep_label)``
      with the peak value and the rank within that tile-position
      (1 = sharpest of the sweeps in the input).
    * ``centre``: ``per_tile`` restricted to ``ix == 0 and iy == 0``,
      pivoted so each row is one sweep and the columns are the four
      methods' ranks (plus the raw peak values).
    """
    df = peaks[peaks["on_target"]].copy()
    df["peak_oriented"] = df.apply(
        lambda r: r["peak_value"] * _orient(r["method"]), axis=1
    )
    df = df.dropna(subset=["peak_oriented"])
    rank = (
        df.groupby(["method", "ix", "iy"])["peak_oriented"]
        .rank(method="min", ascending=False)
        .astype("Int64")
    )
    df["rank"] = rank
    per_tile = df[
        [
            "method",
            "ix",
            "iy",
            "sweep_label",
            "lens",
            "peak_value",
            "rank",
        ]
    ].sort_values(["method", "ix", "iy", "rank"])

    centre = (
        df[(df["ix"] == 0) & (df["iy"] == 0)]
        .pivot_table(
            index=["lens", "sweep_label"],
            columns="method",
            values=["peak_value", "rank"],
        )
        .reset_index()
    )
    centre.columns = ["_".join(filter(None, map(str, c))).strip() for c in centre.columns]
    return {"per_tile": per_tile, "centre": centre}


def centre_method_agreement(per_tile: pd.DataFrame) -> pd.DataFrame:
    """Spearman ρ across methods on the centre-tile ranking of sweeps.

    Returns one row per (method_a, method_b) with the rank correlation.
    """
    centre = per_tile[(per_tile["ix"] == 0) & (per_tile["iy"] == 0)]
    methods = sorted(centre["method"].unique())
    rows = []
    for i, a in enumerate(methods):
        rank_a = (
            centre[centre["method"] == a]
            .set_index("sweep_label")["rank"]
            .sort_index()
        )
        for b in methods[i + 1 :]:
            rank_b = (
                centre[centre["method"] == b]
                .set_index("sweep_label")["rank"]
                .sort_index()
            )
            common = rank_a.index.intersection(rank_b.index)
            if len(common) < 2:
                continue
            from scipy.stats import spearmanr  # local import to keep module light

            rho = float(spearmanr(rank_a.loc[common], rank_b.loc[common]).statistic)
            rows.append({
                "method_a": a,
                "method_b": b,
                "n_sweeps": int(len(common)),
                "spearman_rank_rho": rho,
            })
    return pd.DataFrame(rows)


def symmetric_corner(peaks: pd.DataFrame) -> pd.DataFrame:
    """Pair (ix, iy) with (-ix, -iy) per (sweep, method) and report asymmetry.

    A perfectly-centred lens has matched peaks for opposite tile
    positions. Persistent asymmetry per method = candidate decenter
    signal. We report:

    * ``peak_a``, ``peak_b``: oriented peaks (higher = sharper) at the
      two tile positions.
    * ``rel_diff``: ``(peak_a - peak_b) / max(|peak_a|, |peak_b|)``.
      Sign is preserved so direction matters.
    """
    df = peaks[peaks["on_target"]].copy()
    df["peak_oriented"] = df.apply(
        lambda r: r["peak_value"] * _orient(r["method"]), axis=1
    )
    rows = []
    seen_pairs: set[tuple[int, int]] = set()
    for (ix, iy), _ in df.groupby(["ix", "iy"]):
        if (ix, iy) == (0, 0):
            continue
        if (-ix, -iy) in seen_pairs:
            continue
        seen_pairs.add((ix, iy))
        for (sweep_label, method), grp in df.groupby(["sweep_label", "method"]):
            a = grp[(grp["ix"] == ix) & (grp["iy"] == iy)]
            b = grp[(grp["ix"] == -ix) & (grp["iy"] == -iy)]
            if a.empty or b.empty:
                continue
            pa = float(a["peak_oriented"].iloc[0])
            pb = float(b["peak_oriented"].iloc[0])
            denom = max(abs(pa), abs(pb))
            if denom <= 0:
                continue
            rows.append({
                "sweep_label": sweep_label,
                "method": method,
                "ix": ix,
                "iy": iy,
                "peak_a": pa,
                "peak_b": pb,
                "rel_diff": (pa - pb) / denom,
            })
    return pd.DataFrame(rows)


def run_compare(peaks_csv: Path, out_dir: Path) -> None:
    """End-to-end: load peaks.csv, write cross-lens + symmetry outputs.

    Also emits two plots: a per-tile rank heatmap per method (one
    figure per sweep / lens, since rank is relative to the cohort),
    and a symmetric-corner asymmetry bar chart per method.
    """
    peaks = pd.read_csv(peaks_csv)
    out_dir.mkdir(parents=True, exist_ok=True)

    cl = cross_lens(peaks)
    cl["per_tile"].to_csv(out_dir / "cross_lens_per_tile.csv", index=False)
    cl["centre"].to_csv(out_dir / "cross_lens_centre.csv", index=False)

    agreement = centre_method_agreement(cl["per_tile"])
    agreement.to_csv(out_dir / "cross_lens_centre_agreement.csv", index=False)

    sym = symmetric_corner(peaks)
    sym.to_csv(out_dir / "symmetric_corner.csv", index=False)

    _plot_cross_lens(cl["per_tile"], out_dir / "cross_lens_ranks.png")
    _plot_symmetric_corner(sym, out_dir / "symmetric_corner.png")


def _plot_cross_lens(per_tile: pd.DataFrame, out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    methods = sorted(per_tile["method"].unique())
    sweeps = sorted(per_tile["sweep_label"].unique())
    if not methods or not sweeps:
        return
    n_methods = len(methods)
    n_sweeps = len(sweeps)
    fig, axes = plt.subplots(
        n_sweeps, n_methods, figsize=(3.8 * n_methods, 3.0 * n_sweeps), squeeze=False
    )
    ixs = sorted(per_tile["ix"].unique())
    iys = sorted(per_tile["iy"].unique())
    n_lenses = per_tile.groupby(["method", "ix", "iy"])["rank"].max().max()
    for r, sweep in enumerate(sweeps):
        for c, method in enumerate(methods):
            ax = axes[r, c]
            grid = np.full((len(iys), len(ixs)), np.nan)
            sub = per_tile[
                (per_tile["sweep_label"] == sweep) & (per_tile["method"] == method)
            ]
            for _, row in sub.iterrows():
                grid[iys.index(row["iy"]), ixs.index(row["ix"])] = row["rank"]
            im = ax.imshow(
                grid,
                cmap="viridis_r",
                origin="upper",
                vmin=1,
                vmax=max(int(n_lenses), 2),
            )
            ax.set_xticks([])
            ax.set_yticks([])
            if r == 0:
                ax.set_title(method, fontsize=9)
            if c == 0:
                short = sweep.split("__", 1)[1].split("__1_1")[0]
                ax.set_ylabel(short, fontsize=7)
            plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    fig.suptitle(
        "Cross-lens rank per (method × sweep × tile) — 1 = sharpest of the cohort",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


def _plot_symmetric_corner(sym: pd.DataFrame, out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if sym.empty:
        return
    methods = sorted(sym["method"].unique())
    sweeps = sorted(sym["sweep_label"].unique())
    n_sweeps = len(sweeps)
    fig, axes = plt.subplots(
        n_sweeps, len(methods), figsize=(4 * len(methods), 2.8 * n_sweeps), squeeze=False
    )
    for r, sweep in enumerate(sweeps):
        for c, method in enumerate(methods):
            ax = axes[r, c]
            sub = sym[(sym["sweep_label"] == sweep) & (sym["method"] == method)]
            sub = sub.sort_values(["iy", "ix"])
            labels = [f"({row.ix:+d},{row.iy:+d})" for row in sub.itertuples()]
            values = sub["rel_diff"].to_numpy()
            colors = ["#2b6cb0" if v >= 0 else "#c53030" for v in values]
            ax.bar(range(len(values)), values, color=colors)
            ax.set_xticks(range(len(values)))
            ax.set_xticklabels(labels, rotation=70, fontsize=6)
            ax.axhline(0, color="grey", lw=0.6)
            ax.set_ylim(-0.5, 0.5)
            if r == 0:
                ax.set_title(method, fontsize=9)
            if c == 0:
                short = sweep.split("__", 1)[1].split("__1_1")[0]
                ax.set_ylabel(f"{short}\nrel_diff", fontsize=7)
    fig.suptitle(
        "Symmetric-corner asymmetry — bars away from 0 indicate decenter / tilt",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
