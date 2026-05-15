"""Per-tile-position on/off-target labelling for a sweep.

Two passes:

* **Pass A** picks the peak file size for each tile position across the
  sweep, compares against the best-of-all-peaks, and flags
  ``peak < factor × global_max_peak`` as off-target. Adapts the
  cross-compare idiom from
  :func:`lens_test_detect_core.off_target_by_cross_compare`.
* **Pass B** (tiebreaker) loads one tile near the peak for each
  position whose ``peak / global_max_peak`` lands in an ambiguous band
  and checks the luminance content; tiles that are nearly flat or
  clipped get flagged off-target regardless of file size.

Off-target tile positions are excluded from per-method analysis so
they cannot poison the cross-method comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .geometry import Tile


@dataclass
class TileLabel:
    tile: Tile
    on_target: bool
    reason: str
    peak_bytes: int
    peak_shot_idx: int


def _luminance_stats(path: Path) -> tuple[float, float]:
    img = Image.open(path).convert("L")
    arr = np.asarray(img, dtype=np.float32)
    return float(arr.mean()), float(arr.std())


def label_tiles(
    sizes: dict[Tile, list[int]],
    tile_paths_per_shot: list[dict[Tile, Path]],
    *,
    factor: float = 0.40,
    ambiguous_band: tuple[float, float] = (0.40, 0.60),
    min_std: float = 8.0,
    mean_bounds: tuple[float, float] = (10.0, 245.0),
) -> dict[Tile, TileLabel]:
    """Label each tile position as on/off-target.

    ``sizes`` maps a tile position to its file-size sequence across the
    sweep (one entry per shot in shot-order). ``tile_paths_per_shot``
    is the parallel sequence of per-shot tile-path maps used for the
    Pass B content check.
    """
    if not sizes:
        return {}

    peaks: dict[Tile, tuple[int, int]] = {
        t: (max(range(len(seq)), key=seq.__getitem__), max(seq)) for t, seq in sizes.items()
    }
    global_max = max(p[1] for p in peaks.values())
    cutoff_low = factor * global_max
    amb_lo, amb_hi = ambiguous_band[0] * global_max, ambiguous_band[1] * global_max

    out: dict[Tile, TileLabel] = {}
    for tile, (peak_idx, peak_bytes) in peaks.items():
        if peak_bytes < cutoff_low:
            out[tile] = TileLabel(
                tile=tile,
                on_target=False,
                reason=f"peak_below_factor (peak={peak_bytes} < {cutoff_low:.0f})",
                peak_bytes=peak_bytes,
                peak_shot_idx=peak_idx,
            )
            continue
        if amb_lo <= peak_bytes < amb_hi:
            shot_paths = tile_paths_per_shot[peak_idx]
            try:
                mean, std = _luminance_stats(shot_paths[tile])
            except (OSError, KeyError):
                out[tile] = TileLabel(
                    tile=tile,
                    on_target=False,
                    reason="content_read_failed",
                    peak_bytes=peak_bytes,
                    peak_shot_idx=peak_idx,
                )
                continue
            if std < min_std:
                out[tile] = TileLabel(
                    tile=tile,
                    on_target=False,
                    reason=f"flat_content (std={std:.1f})",
                    peak_bytes=peak_bytes,
                    peak_shot_idx=peak_idx,
                )
                continue
            if mean < mean_bounds[0] or mean > mean_bounds[1]:
                out[tile] = TileLabel(
                    tile=tile,
                    on_target=False,
                    reason=f"clipped_content (mean={mean:.1f})",
                    peak_bytes=peak_bytes,
                    peak_shot_idx=peak_idx,
                )
                continue
        out[tile] = TileLabel(
            tile=tile,
            on_target=True,
            reason="ok",
            peak_bytes=peak_bytes,
            peak_shot_idx=peak_idx,
        )
    return out
