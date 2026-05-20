"""Cross-lens visual-inspection artefact.

Two export modes — one per peaks-CSV format:

* ``export_cross_lens_crops(peaks_csv, ...)`` — legacy 8-method
  POC source (``peaks.csv``). Emits one crop per (method, lens, tile)
  to ``cross_lens_crops/tile_<ix>_<iy>/<method>__<lens>__shot_<k>.jpg``
  so the human can spot disagreements between methods.

* ``export_peaks_v2_crops(peaks_v2_csv, ...)`` — new pipeline
  (``peaks_v2.csv``). Emits one crop per (lens, tile) using the
  primary-metric argmax (maze-FFT amp at M≥0.7, scribe-LSF peak amp
  otherwise) to ``peaks_v2_crops/tile_<ix>_<iy>/<lens>__shot_<k>.jpg``.
  Replaces filesize-picked legacy crops that systematically miss true
  focus on sharp configs (HANDOVER warning re: ``out_55mm/cross_lens_crops``).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from .crop import extract_tiles
from .geometry import Tile
from .methods import METHODS
from .sweeps import discover_all, discover_newer, discover_older


def _discover_for_sweep_ids(sweep_ids: list[str]) -> dict[str, "Sweep"]:
    """Skip slow discovery walks for sweep families that don't appear in the input.

    The CLI ``peaks-v2-crops`` on an older-rig-only cohort would
    otherwise scan ``~/macro-lens-test-output/`` (65+ session dirs)
    pointlessly. Inspect the sweep IDs to decide which discovery
    functions to invoke.
    """
    families_needed = {sid.split("/", 1)[0] for sid in sweep_ids if "/" in sid}
    need_newer = "newer-rig" in families_needed
    need_older = any(f.startswith("older-") for f in families_needed)
    sweeps: list = []
    if need_older and need_newer:
        sweeps = discover_all()
    elif need_older:
        sweeps = discover_older()
    elif need_newer:
        sweeps = discover_newer()
    else:
        sweeps = discover_all()
    return {s.id: s for s in sweeps}


def export_cross_lens_crops(
    peaks_csv: Path,
    out_dir: Path,
    tile_positions: list[tuple[int, int]] | None = None,
) -> None:
    """Copy peak-tile crops to ``out_dir / tile_<ix>_<iy>/`` per method × lens."""
    peaks = pd.read_csv(peaks_csv)
    peaks = peaks[peaks["on_target"]]
    if tile_positions is None:
        tile_positions = [(0, 0)]

    sweeps = {s.id: s for s in discover_all()}

    for ix, iy in tile_positions:
        sub = peaks[(peaks["ix"] == ix) & (peaks["iy"] == iy)]
        if sub.empty:
            continue
        tile_dir = out_dir / f"tile_{ix:+d}_{iy:+d}"
        tile_dir.mkdir(parents=True, exist_ok=True)
        readme_lines = [
            f"Tile position ix={ix} iy={iy}",
            "Each row is one (method, lens) pair, showing the rail step "
            "that method picked as the per-lens argmax.",
            "",
        ]
        for _, row in sub.sort_values(["method", "lens"]).iterrows():
            method = row["method"]
            sweep_id = row["sweep_id"]
            argmax_idx = int(row["argmax_idx"])
            if argmax_idx < 0 or pd.isna(row["peak_value"]):
                readme_lines.append(
                    f"  {method:12s}  {row['lens']:40s}  (no value)"
                )
                continue
            sweep = sweeps.get(sweep_id)
            if sweep is None or argmax_idx >= len(sweep.shots):
                continue
            shot = sweep.shots[argmax_idx]
            tile = Tile(
                ix=ix,
                iy=iy,
                x=int(row["x"]),
                y=int(row["y"]),
                size=int(row["tile_size"]),
            )
            tile_paths = extract_tiles(shot.path, [tile])
            src = tile_paths[0].path
            safe_lens = row["lens"].replace(" ", "_").replace("/", "_")
            dst = tile_dir / f"{method}__{safe_lens}__shot_{argmax_idx:03d}.jpg"
            if not dst.exists():
                shutil.copy(src, dst)
            orient = METHODS[method].orientation
            sign = "↑" if orient == "higher_is_sharper" else "↓"
            readme_lines.append(
                f"  {method:12s}  {row['lens']:40s}  shot={argmax_idx:3d}  "
                f"peak={row['peak_value']:.5g}{sign}"
            )
        (tile_dir / "README.txt").write_text("\n".join(readme_lines) + "\n")


def export_peaks_v2_crops(
    peaks_v2_csv: Path,
    out_dir: Path,
    tile_positions: list[tuple[int, int]] | None = None,
) -> None:
    """Copy primary-metric argmax crops to ``out_dir / tile_<ix>_<iy>/<lens>__shot_<k>.jpg``.

    Reads the new pipeline's ``peaks_v2.csv`` (single argmax per
    (sweep, tile_ix, tile_iy) picked by maze-FFT amp or scribe-LSF
    amp depending on M). One JPEG per (lens, tile) — no per-method
    dimension since v2 uses one primary metric per tile.

    Tiles are cropped at the per-shot row's ``tile_x_px``,
    ``tile_y_px``, ``lsf_roi_px`` / ``maze_roi_px`` recorded in the
    CSV. The crop size follows the legacy 1024-px tile cache for the
    saved JPEG to keep visual comparisons consistent — the larger
    M-driven ROIs are used by the numerical pipeline, not the human-
    visible artefact.
    """
    peaks = pd.read_csv(peaks_v2_csv)
    if tile_positions is None:
        tile_positions = [(0, 0)]

    sweeps = _discover_for_sweep_ids(peaks["sweep"].unique().tolist())

    for ix, iy in tile_positions:
        sub = peaks[(peaks["tile_ix"] == ix) & (peaks["tile_iy"] == iy)]
        if sub.empty:
            continue
        tile_dir = out_dir / f"tile_{ix:+d}_{iy:+d}"
        tile_dir.mkdir(parents=True, exist_ok=True)
        readme_lines = [
            f"Tile position ix={ix} iy={iy}",
            "One crop per lens, taken at the v2 pipeline's primary-metric "
            "argmax shot (maze-FFT amp at M≥0.7, scribe-LSF amp otherwise).",
            "",
        ]
        for _, row in sub.sort_values("sweep").iterrows():
            sweep_id = row["sweep"]
            argmax_idx = int(row["argmax_shot_idx"])
            primary = row.get("primary_metric_used", "?")
            peak_value = row.get("peak_value")
            mtf50_subj = row.get("mtf50_subject_lp_per_mm")
            sweep = sweeps.get(sweep_id)
            if sweep is None or argmax_idx < 0 or argmax_idx >= len(sweep.shots):
                readme_lines.append(
                    f"  {sweep_id:80s}  (no source shot for shot_idx={argmax_idx})"
                )
                continue
            shot = sweep.shots[argmax_idx]
            tile = Tile(
                ix=ix, iy=iy,
                x=int(row["tile_x_px"]),
                y=int(row["tile_y_px"]),
                size=1024,
            )
            tile_paths = extract_tiles(shot.path, [tile])
            src = tile_paths[0].path
            safe_lens = str(sweep_id).split("/")[-1].replace(" ", "_").replace("/", "_")
            dst = tile_dir / f"{safe_lens}__shot_{argmax_idx:03d}.jpg"
            if not dst.exists():
                shutil.copy(src, dst)
            readme_lines.append(
                f"  {str(sweep_id)[:80]:80s}  shot={argmax_idx:3d}  "
                f"primary={primary:10s}  peak={float(peak_value):.5g}  "
                f"mtf50_subj={float(mtf50_subj) if pd.notna(mtf50_subj) else float('nan'):.2f} lp/mm"
            )
        (tile_dir / "README.txt").write_text("\n".join(readme_lines) + "\n")
