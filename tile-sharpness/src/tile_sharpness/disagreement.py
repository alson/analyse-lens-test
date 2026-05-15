"""Curated disagreement-sample export.

For each sweep, find the tile positions where the active methods most
disagree on the argmax rail step (peak position), and dump each
method's argmax tile JPEG into a per-tile directory for manual
side-by-side review. We also include the centre tile of each method's
chosen shot so the human can spot-check the surrounding context.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np

from .analyse import SweepResult
from .crop import extract_tiles
from .geometry import Tile


def _disagreement_score(argmaxes: list[int], n_shots: int) -> float:
    """Spread of argmax across methods, normalised to ``[0, 1]``.

    Empty list ⇒ 0. Single method ⇒ 0. Otherwise the population
    standard deviation of the indices, divided by the max possible
    spread (half the sweep length).
    """
    if len(argmaxes) < 2:
        return 0.0
    spread = float(np.std(argmaxes))
    return spread / max(n_shots / 2.0, 1.0)


def export_disagreement(
    result: SweepResult,
    out_dir: Path,
    *,
    top_k: int = 8,
) -> list[tuple[Tile, float]]:
    """Write tile-level disagreement samples for one sweep.

    Returns the ranked ``(tile, score)`` list (descending) of the
    positions we exported, so callers can summarise across sweeps.
    """
    on_target = [t for t, lbl in result.labels.items() if lbl.on_target]
    n_shots = len(result.sweep.shots)
    scored: list[tuple[Tile, float, dict[str, int]]] = []
    for tile in on_target:
        argmaxes_per_method: dict[str, int] = {}
        for key, peaks in result.peaks.items():
            _, argmax_i = peaks.get(tile, (float("nan"), -1))
            if argmax_i >= 0:
                argmaxes_per_method[key] = argmax_i
        if len(argmaxes_per_method) < 2:
            continue
        score = _disagreement_score(list(argmaxes_per_method.values()), n_shots)
        scored.append((tile, score, argmaxes_per_method))

    scored.sort(key=lambda item: item[1], reverse=True)
    selected = scored[:top_k]

    sweep_dir = out_dir / "disagreement" / _safe(result.sweep.label)
    sweep_dir.mkdir(parents=True, exist_ok=True)

    for tile, score, argmaxes_per_method in selected:
        tile_dir = sweep_dir / f"tile_{tile.ix:+d}_{tile.iy:+d}"
        tile_dir.mkdir(parents=True, exist_ok=True)

        # Identify the set of distinct shots picked by any method. Save
        # each one's tile JPEG (already cached on disk) once.
        unique_shots = sorted(set(argmaxes_per_method.values()))
        for shot_idx in unique_shots:
            shot = result.sweep.shots[shot_idx]
            tile_paths = extract_tiles(shot.path, [tile])
            src_path = tile_paths[0].path
            dst = tile_dir / f"shot_{shot_idx:03d}__{shot.path.stem}.jpg"
            if not dst.exists():
                shutil.copy(src_path, dst)

        readme = tile_dir / "README.txt"
        lines = [
            f"sweep: {result.sweep.label}",
            f"family: {result.sweep.family}",
            f"tile: ix={tile.ix} iy={tile.iy} size={tile.size} origin=({tile.x},{tile.y})",
            f"disagreement_score: {score:.4f}",
            "",
            "Per-method argmax:",
        ]
        for key, argmax_i in sorted(argmaxes_per_method.items()):
            peak_v, _ = result.peaks[key][tile]
            shot = result.sweep.shots[argmax_i]
            rail_mm = (
                f"{shot.rail_position_mm:.3f} mm"
                if shot.rail_position_mm is not None
                else "(rail mm unknown)"
            )
            lines.append(
                f"  {key:12s}  argmax_idx={argmax_i:3d}  rail={rail_mm}  "
                f"peak={peak_v:.4g}  pick={shot.path.name}"
            )
        readme.write_text("\n".join(lines) + "\n")
    return [(t, s) for t, s, _ in selected]


def _safe(name: str) -> str:
    return name.replace("/", "_")
