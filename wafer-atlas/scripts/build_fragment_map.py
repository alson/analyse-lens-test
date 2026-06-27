"""Build the wafer FRAGMENT-OUTLINE prior: a per-die-cell wafer-coverage map in
grid (col, row) coordinates, derived from the low-M sweep1 which shows the whole
fragment and is registered (anchor affine). This is the "whole-vs-jagged"
inventory the handover called for, grounded in real data instead of hand-listed.

For each physical die cell (col 0..10, row A..F = 0..5) we map a grid of (u,v)
points inside the cell to sweep1 image pixels via the affine, and average the
wafer mask there. coverage ~1 = whole die, ~0 = absent (off-wafer), in between =
partial/nicked. Saved to out/fragment_map.json + an overlay PNG.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).parent
A = HERE.parent
OUT = A / "out" / "diag_2026_06"


def _load(m, f):
    s = importlib.util.spec_from_file_location(m, HERE / f)
    x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x


mm = _load("mm", "register_method_morphological.py")
af = _load("af", "anchor_fit_sweep.py")
ra = _load("ra", "reg_auto.py")

ATLAS = json.load(open(A / "atlas.json"))
ANCHORS = json.load(open(A / "out" / "sweep_anchors" / "anchor_fit_params.json"))
N_COL, N_ROW = 11, 6   # die columns 0..10, die rows A..F (0..5)


def cell_coverage(wafer_full, p, col, row, n=5):
    """Mean wafer coverage over an n×n grid of (u,v) points inside die (col,row),
    in the full-res image, using sweep1's affine. wafer_full is the FULL-RES
    wafer mask; we sample it."""
    H, W = wafer_full.shape
    us = np.linspace(0.15, 0.85, n)
    vs = np.linspace(0.15, 0.85, n)
    hits, tot = 0, 0
    for u in us:
        for v in vs:
            x, y = af.grid_xy(col + u, row + v, p, ATLAS)
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < W and 0 <= yi < H:
                hits += int(wafer_full[yi, xi]); tot += 1
            else:
                tot += 1   # out of frame counts as not-covered (fragment may extend out)
    return hits / tot if tot else 0.0


def main():
    sweep1_path = ra.SWEEPS["sweep1_M0.385"][0]
    p = ANCHORS["sweep1_M0.385"]
    # full-res wafer mask: segment on full-res gray (downscale factor handled by
    # affine which is in full-res coords; segment full-res for accurate coverage)
    from PIL import Image
    img = np.asarray(Image.open(sweep1_path).convert("L"))
    # wafer_mask works on any grayscale; run on a 2x-downsampled copy for speed,
    # then upsample mask back (coverage is coarse anyway)
    import cv2
    small = cv2.resize(img, (img.shape[1] // 4, img.shape[0] // 4), interpolation=cv2.INTER_AREA)
    wafer_small, _ = ra.wafer_mask(small)
    wafer_full = cv2.resize(wafer_small, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)

    cov = {}
    grid = np.full((N_ROW, N_COL), np.nan)
    for col in range(N_COL):
        for row in range(N_ROW):
            c = cell_coverage(wafer_full, p, col, row)
            cov[f"{col},{row}"] = round(c, 3)
            grid[row, col] = c

    fragment_outline = {
        "source": "sweep1_M0.385 (whole-fragment, anchor-registered)",
        "built": "2026-06-27",
        "n_col": N_COL, "n_row": N_ROW,
        "note": ("per physical die cell wafer coverage; 1=whole, 0=absent "
                 "(off-wafer), mid=jagged/partial. Keys 'col,row' with col 0..10 "
                 "left->right and row 0..5 = A..F bottom->top. Used to "
                 "disambiguate the absolute column offset in autonomous "
                 "registration (reg_auto.fragment_disambiguate)."),
        "coverage": cov,
    }
    # CANONICAL store: write into atlas.json (promotes the old whole-vs-jagged
    # follow-up into the atlas). Keep a copy under out/ for convenience.
    atlas_path = A / "atlas.json"
    atlas = json.load(open(atlas_path))
    atlas["fragment_outline"] = fragment_outline
    atlas["schema_version"] = max(atlas.get("schema_version", 1), 2)
    json.dump(atlas, open(atlas_path, "w"), indent=2)
    json.dump(fragment_outline, open(A / "out" / "fragment_map.json", "w"), indent=1)

    print("Fragment coverage map (rows F..A top..bottom, cols 0..10):")
    print("      " + " ".join(f"c{c:<3}" for c in range(N_COL)))
    for row in range(N_ROW - 1, -1, -1):
        cells = " ".join(f"{grid[row,col]:.2f}" for col in range(N_COL))
        print(f"  r{'ABCDEF'[row]}: {cells}")

    fig, ax = plt.subplots(1, 2, figsize=(20, 7))
    ax[0].imshow(img, cmap="gray")
    ax[0].imshow(np.ma.masked_where(wafer_full == 1, wafer_full), cmap="autumn", alpha=0.4)
    for col in range(N_COL):
        for row in range(N_ROW):
            x, y = af.grid_xy(col + 0.5, row + 0.5, p, ATLAS)
            if 0 < x < img.shape[1] and 0 < y < img.shape[0]:
                ax[0].text(x, y, f"{col}{'ABCDEF'[row]}\n{grid[row,col]:.2f}",
                           color="lime", fontsize=7, ha="center", va="center")
    ax[0].set_title("sweep1 + off-wafer (red) + per-cell coverage")
    im = ax[1].imshow(grid, cmap="RdYlGn", vmin=0, vmax=1, origin="lower")
    ax[1].set_xticks(range(N_COL)); ax[1].set_yticks(range(N_ROW))
    ax[1].set_yticklabels(list("ABCDEF"))
    ax[1].set_xlabel("die col"); ax[1].set_title("fragment coverage map (green=whole, red=absent)")
    for col in range(N_COL):
        for row in range(N_ROW):
            ax[1].text(col, row, f"{grid[row,col]:.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax[1]); fig.tight_layout()
    fig.savefig(OUT / "fragment_map.png", dpi=100)
    print(f"\npromoted fragment_outline into atlas.json (schema_version -> 2); "
          f"copy at out/fragment_map.json; overlay at out/diag_2026_06/fragment_map.png")


if __name__ == "__main__":
    main()
