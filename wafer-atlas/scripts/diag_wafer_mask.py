"""Wafer-region segmentation via TEXTURE (per the user's insight: the wafer edge
is a long, high-contrast, non-grid-aligned boundary; the wafer is the textured
region, off-wafer is not).

Method:
  1. local-std texture map; wafer = textured.
  2. close + keep largest component + FILL INTERIOR HOLES (so smooth die regions,
     which are holes inside the wafer, do NOT get mistaken for background).
  3. off-wafer = border-connected non-wafer. A frame side that is not fully
     covered by wafer has the wafer edge in view.
  4. report the wafer-boundary contour that lies INSIDE the frame (the fracture
     edge): its length and how non-straight it is (max deviation from its
     endpoints' chord) — a scribe would be straight, the fracture is not.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).parent
OUT = HERE.parent / "out" / "diag_2026_06"
mm = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("mm", HERE / "register_method_morphological.py"))
importlib.util.spec_from_file_location("mm", HERE / "register_method_morphological.py").loader.exec_module(mm)
ra = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("ra", HERE / "reg_auto.py"))
importlib.util.spec_from_file_location("ra", HERE / "reg_auto.py").loader.exec_module(ra)


def wafer_mask(g):
    """Return (wafer_mask uint8, off_wafer uint8). Wafer = largest textured
    region with interior holes filled."""
    g = g.astype(np.float32)
    k = 13
    mean = cv2.boxFilter(g, -1, (k, k))
    sq = cv2.boxFilter(g * g, -1, (k, k))
    std = np.sqrt(np.maximum(sq - mean * mean, 0))
    textured = (std > max(4.0, np.percentile(std, 35))).astype(np.uint8)
    # bridge thin scribe gaps (~5 px) but NOT the larger off-wafer corner gaps;
    # interior smooth die regions are filled later by border flood-fill, not here.
    textured = cv2.morphologyEx(textured, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    textured = cv2.morphologyEx(textured, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(textured, 8)
    if n <= 1:
        return textured, 1 - textured
    wafer = (lbl == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    # fill interior holes (smooth die regions): flood non-wafer from the border;
    # whatever non-wafer is NOT reached from the border is an interior hole.
    h, w = wafer.shape
    inv = (1 - wafer).astype(np.uint8)
    ff = inv.copy()
    mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ff, mask, (0, 0), 0)          # border-connected non-wafer -> 0
    holes = ff                                   # remaining 1s = interior holes
    wafer_filled = (wafer | holes).astype(np.uint8)
    off = (1 - wafer_filled).astype(np.uint8)
    return wafer_filled, off


def side_coverage(wafer):
    """Fraction of each frame side covered by wafer (1.0 = no edge there)."""
    h, w = wafer.shape
    b = max(3, int(0.02 * min(h, w)))
    return {"left": float(wafer[:, :b].mean()), "right": float(wafer[:, -b:].mean()),
            "top": float(wafer[:b, :].mean()), "bottom": float(wafer[-b:, :].mean())}


def main():
    for name, (path, anchors) in ra.SWEEPS.items():
        g, _, _ = mm.load_gray_downscaled(path)
        wafer, off = wafer_mask(g)
        cov = side_coverage(wafer)
        edges_in_view = {k: round(1 - v, 3) for k, v in cov.items()}
        print(f"{name}: wafer side-coverage {{ {', '.join(f'{k}:{v:.2f}' for k,v in cov.items())} }}"
              f"  -> edge-in-view (1-cov) {edges_in_view}  off-wafer area={off.mean():.3f}")
        fig, ax = plt.subplots(1, 2, figsize=(13, 5))
        ax[0].imshow(g, cmap="gray"); ax[0].set_title(f"{name}")
        ax[1].imshow(g, cmap="gray")
        ax[1].imshow(np.ma.masked_where(off == 0, off), cmap="autumn", alpha=0.55)
        ax[1].set_title(f"off-wafer (red). edge-in-view={edges_in_view}")
        fig.tight_layout(); fig.savefig(OUT / f"{name}_wafermask.png", dpi=90); plt.close(fig)


if __name__ == "__main__":
    main()
