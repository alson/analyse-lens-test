"""Cross-lens visual-inspection artefact.

For each tile position the user cares about (default: centre tile),
for each method, copy the peak-shot tile JPEG from each lens into a
single side-by-side directory so the human can judge which lens is
actually sharpest under each method's verdict.

Layout::

    cross_lens_crops/
      tile_<ix>_<iy>/
        filesize__<lens>__shot_<k>.jpg
        mtfmapper__<lens>__shot_<k>.jpg
        radial_fft__<lens>__shot_<k>.jpg
        edge_decay__<lens>__shot_<k>.jpg
        README.txt

The README captures the per-lens peak metric values and argmax shot
index so the user can correlate visual sharpness to numbers.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from .crop import extract_tiles
from .geometry import Tile
from .methods import METHODS
from .sweeps import discover_all


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
