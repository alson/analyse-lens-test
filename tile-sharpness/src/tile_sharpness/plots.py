"""Per-sweep and cross-sweep summary plots.

Per-sweep figure: one column per active method, two rows: peak heatmap
(metric value, normalised per method) and argmax heatmap (rail-step
index, common 0..N-1 colour scale per sweep). Off-target tiles are
shaded grey.

Cross-sweep summary: scatter of Spearman ρ on peaks and on argmax for
every method-pair, one point per sweep.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .analyse import SweepResult
from .geometry import Tile, grid_shape
from .methods import METHODS


def _grid_array(
    tiles: list[Tile],
    value_for: dict[Tile, float],
    fill: float = np.nan,
) -> np.ndarray:
    ixs = [t.ix for t in tiles]
    iys = [t.iy for t in tiles]
    x_min, y_min = min(ixs), min(iys)
    w, h = grid_shape(tiles)
    grid = np.full((h, w), fill, dtype=float)
    for t in tiles:
        grid[t.iy - y_min, t.ix - x_min] = value_for.get(t, fill)
    return grid


def plot_sweep(result: SweepResult, out_path: Path) -> None:
    methods = list(result.peaks.keys())
    n = max(len(methods), 1)
    fig, axes = plt.subplots(2, n, figsize=(4.5 * n, 7.5), squeeze=False)
    fig.suptitle(result.sweep.label, fontsize=10)

    on_target = {t for t, lbl in result.labels.items() if lbl.on_target}

    for col, key in enumerate(methods):
        spec = METHODS[key]
        peaks = result.peaks[key]

        peak_vals: dict[Tile, float] = {}
        argmax_vals: dict[Tile, float] = {}
        for tile, (peak_v, argmax_i) in peaks.items():
            if tile not in on_target or argmax_i < 0:
                continue
            peak_vals[tile] = peak_v
            argmax_vals[tile] = float(argmax_i)

        peak_grid = _grid_array(result.tiles, peak_vals)
        argmax_grid = _grid_array(result.tiles, argmax_vals)

        ax_peak = axes[0, col]
        cmap_peak = "viridis" if spec.orientation == "higher_is_sharper" else "viridis_r"
        im_peak = ax_peak.imshow(peak_grid, cmap=cmap_peak, origin="upper")
        ax_peak.set_title(f"{spec.label}\n(peak)", fontsize=9)
        ax_peak.set_xticks([])
        ax_peak.set_yticks([])
        plt.colorbar(im_peak, ax=ax_peak, fraction=0.04, pad=0.02)

        ax_arg = axes[1, col]
        n_shots = len(result.sweep.shots)
        im_arg = ax_arg.imshow(
            argmax_grid,
            cmap="plasma",
            origin="upper",
            vmin=0,
            vmax=max(n_shots - 1, 1),
        )
        ax_arg.set_title(f"{spec.label}\n(argmax rail step)", fontsize=9)
        ax_arg.set_xticks([])
        ax_arg.set_yticks([])
        plt.colorbar(im_arg, ax=ax_arg, fraction=0.04, pad=0.02)

    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_agreement_summary(agreement: pd.DataFrame, out_path: Path) -> None:
    if agreement.empty:
        return
    pairs = sorted(agreement[["method_a", "method_b"]].apply(tuple, axis=1).unique())
    n = len(pairs)
    fig, axes = plt.subplots(1, max(n, 1), figsize=(4 * max(n, 1), 4), squeeze=False)
    for i, (a, b) in enumerate(pairs):
        ax = axes[0, i]
        rows = agreement[(agreement.method_a == a) & (agreement.method_b == b)]
        ax.scatter(rows.spearman_peak, rows.argmax_match_within_1, alpha=0.6)
        ax.set_xlabel(f"Spearman ρ peak\n({a} vs {b})", fontsize=9)
        ax.set_ylabel("argmax match (±1) fraction", fontsize=9)
        ax.set_xlim(-1.05, 1.05)
        ax.set_ylim(-0.05, 1.05)
        ax.axhline(0, color="grey", lw=0.5)
        ax.axvline(0, color="grey", lw=0.5)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
