"""Sweep-level aggregation across methods.

The aggregation collapses one sweep into a per-(method, tile-position)
``(peak, argmax)`` pair. ``peak`` is the maximum (or minimum, depending
on the method orientation) of the smoothed metric across the sweep;
``argmax`` is the rail step at which that peak occurred. The
``argmax`` map across the grid is the field-tilt/curvature fingerprint
we'll compare across methods.

CSV outputs:

* ``peaks.csv`` — one row per (sweep, method, ix, iy), with raw and
  smoothed peak values, argmax rail step, and on-target flag.
* ``agreement.csv`` — one row per (sweep, method_a, method_b), with
  Spearman ρ on the per-tile peak rank, Spearman ρ on the per-tile
  argmax rank, and the fraction of tiles where argmax matches within
  ±1 rail step.
"""

from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from lens_test_detect_core import smooth
from scipy.stats import spearmanr

from .crop import DEFAULT_CACHE_ROOT, extract_tiles, image_dimensions
from .geometry import Tile, compute_tiles
from .methods import METHODS, MethodSpec
from .on_target import TileLabel, label_tiles
from .sweeps import Sweep


SMOOTH_WINDOW = 3


@dataclass
class SweepResult:
    sweep: Sweep
    tiles: list[Tile]
    labels: dict[Tile, TileLabel]
    metrics: dict[str, dict[Tile, np.ndarray]] = field(default_factory=dict)
    peaks: dict[str, dict[Tile, tuple[float, int]]] = field(default_factory=dict)


def _extract_for_sweep(
    sweep: Sweep, tile_size: int, cache_root: Path
) -> tuple[list[Tile], list[dict[Tile, Path]]]:
    w, h = image_dimensions(sweep.shots[0].path)
    tiles = compute_tiles(w, h, tile_size)
    per_shot: list[dict[Tile, Path]] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda s: extract_tiles(s.path, tiles, cache_root=cache_root),
                sweep.shots,
            )
        )
    for tile_paths in results:
        per_shot.append({tp.tile: tp.path for tp in tile_paths})
    return tiles, per_shot


def _score_method(
    method: MethodSpec,
    tile_paths_per_shot: list[dict[Tile, Path]],
    on_target_tiles: list[Tile],
    *,
    workers: int = 4,
) -> dict[Tile, np.ndarray]:
    """Run ``method.scorer`` across the sweep for each on-target tile."""
    n = len(tile_paths_per_shot)
    out: dict[Tile, np.ndarray] = {}

    # Flatten work units so the worker pool can parallelise across the
    # cross-product of (tile, shot). Each scorer call is independent.
    jobs: list[tuple[Tile, int, Path]] = [
        (tile, k, tile_paths_per_shot[k][tile])
        for tile in on_target_tiles
        for k in range(n)
    ]
    result_buf: dict[Tile, np.ndarray] = {
        tile: np.full(n, np.nan, dtype=float) for tile in on_target_tiles
    }

    def _run(job: tuple[Tile, int, Path]) -> tuple[Tile, int, float | None]:
        tile, k, path = job
        return tile, k, method.scorer(path)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for tile, k, v in pool.map(_run, jobs):
            if v is not None:
                result_buf[tile][k] = v
    out.update(result_buf)
    return out


def _argmax_with_smoothing(
    series: np.ndarray, method: MethodSpec, window: int = SMOOTH_WINDOW
) -> tuple[float, int]:
    """Return ``(peak_value, raw_index)`` of the smoothed series."""
    if not np.any(np.isfinite(series)):
        return float("nan"), -1
    valid_mask = np.isfinite(series)
    # Replace NaNs with sentinel so the smoothing window doesn't propagate
    # them — use the worst (least sharp) value the method has produced.
    if method.orientation == "higher_is_sharper":
        worst = np.nanmin(series)
        clean = np.where(valid_mask, series, worst)
    else:
        worst = np.nanmax(series)
        clean = np.where(valid_mask, series, worst)
    smoothed = smooth(clean, window=window)
    if smoothed.size == 0:
        idx = int(np.nanargmax(series) if method.orientation == "higher_is_sharper" else np.nanargmin(series))
        return float(series[idx]), idx
    offset = (window - 1) // 2
    if method.orientation == "higher_is_sharper":
        smoothed_idx = int(np.argmax(smoothed))
    else:
        smoothed_idx = int(np.argmin(smoothed))
    raw_idx = smoothed_idx + offset
    return float(series[raw_idx]), raw_idx


def analyse_sweep(
    sweep: Sweep,
    *,
    tile_size: int = 1024,
    methods: Iterable[str] = ("filesize", "mtfmapper", "radial_fft", "edge_decay"),
    cache_root: Path = DEFAULT_CACHE_ROOT,
    workers: int = 4,
) -> SweepResult:
    tiles, per_shot = _extract_for_sweep(sweep, tile_size, cache_root)

    sizes: dict[Tile, list[int]] = {
        tile: [shot[tile].stat().st_size for shot in per_shot] for tile in tiles
    }
    labels = label_tiles(sizes, per_shot)
    on_target = [t for t, lbl in labels.items() if lbl.on_target]

    result = SweepResult(sweep=sweep, tiles=tiles, labels=labels)
    for key in methods:
        if key not in METHODS:
            raise KeyError(f"unknown method {key!r}; have {list(METHODS)}")
        spec = METHODS[key]
        series_by_tile = _score_method(spec, per_shot, on_target, workers=workers)
        # File-size is "free" — we have the bytes already from the sizes
        # dict; reuse to avoid stat() round-trips.
        if key == "filesize":
            for tile in on_target:
                series_by_tile[tile] = np.asarray(sizes[tile], dtype=float)
        result.metrics[key] = series_by_tile
        peaks: dict[Tile, tuple[float, int]] = {}
        for tile, series in series_by_tile.items():
            peaks[tile] = _argmax_with_smoothing(series, spec)
        result.peaks[key] = peaks
    return result


def peaks_dataframe(results: list[SweepResult]) -> pd.DataFrame:
    rows = []
    for res in results:
        for tile in res.tiles:
            label = res.labels[tile]
            row_base = {
                "sweep_id": res.sweep.id,
                "sweep_label": res.sweep.label,
                "family": res.sweep.family,
                "lens": res.sweep.lens,
                "aperture": res.sweep.aperture,
                "ix": tile.ix,
                "iy": tile.iy,
                "x": tile.x,
                "y": tile.y,
                "tile_size": tile.size,
                "on_target": label.on_target,
                "label_reason": label.reason,
                "peak_bytes": label.peak_bytes,
            }
            for method_key, peaks in res.peaks.items():
                if tile not in peaks:
                    continue
                peak_value, argmax_idx = peaks[tile]
                rail_mm = (
                    res.sweep.shots[argmax_idx].rail_position_mm
                    if 0 <= argmax_idx < len(res.sweep.shots)
                    else None
                )
                rows.append({
                    **row_base,
                    "method": method_key,
                    "peak_value": peak_value,
                    "argmax_idx": argmax_idx,
                    "argmax_rail_mm": rail_mm,
                })
    return pd.DataFrame(rows)


def agreement_dataframe(results: list[SweepResult]) -> pd.DataFrame:
    """Pairwise method-vs-method agreement per sweep, on-target tiles only."""
    rows = []
    for res in results:
        ot = [t for t, lbl in res.labels.items() if lbl.on_target]
        if len(ot) < 3:
            continue
        method_keys = list(res.peaks.keys())
        # Build per-method aligned peak and argmax arrays over on-target tiles.
        peak_arrays: dict[str, np.ndarray] = {}
        argmax_arrays: dict[str, np.ndarray] = {}
        for k in method_keys:
            pv = np.array([res.peaks[k][t][0] for t in ot])
            ai = np.array([res.peaks[k][t][1] for t in ot])
            # Flip lower-is-better so all comparisons are "higher rank = sharper".
            if METHODS[k].orientation == "lower_is_sharper":
                pv = -pv
            peak_arrays[k] = pv
            argmax_arrays[k] = ai
        for i, a in enumerate(method_keys):
            for b in method_keys[i + 1 :]:
                pa, pb = peak_arrays[a], peak_arrays[b]
                aa, ab = argmax_arrays[a], argmax_arrays[b]
                mask = np.isfinite(pa) & np.isfinite(pb) & (aa >= 0) & (ab >= 0)
                n = int(mask.sum())
                if n < 3:
                    rho_peak = rho_arg = exact = float("nan")
                else:
                    rho_peak = float(spearmanr(pa[mask], pb[mask]).statistic)
                    rho_arg = float(spearmanr(aa[mask], ab[mask]).statistic)
                    exact = float(np.mean(np.abs(aa[mask] - ab[mask]) <= 1))
                rows.append({
                    "sweep_id": res.sweep.id,
                    "sweep_label": res.sweep.label,
                    "family": res.sweep.family,
                    "method_a": a,
                    "method_b": b,
                    "n_tiles": n,
                    "spearman_peak": rho_peak,
                    "spearman_argmax": rho_arg,
                    "argmax_match_within_1": exact,
                })
    return pd.DataFrame(rows)
