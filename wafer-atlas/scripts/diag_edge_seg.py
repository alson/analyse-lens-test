"""Diagnose wafer/background segmentation per sweep, on the ORIGINAL (non-de-
rotated) downsampled image so the de-rotation reflect-fill can't corrupt the
corners. Visualize: gray, local-std texture, smooth mask, border-touching
background components, and per-edge background fraction.
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


def texture_std(g, k=13):
    g = g.astype(np.float32)
    mean = cv2.boxFilter(g, -1, (k, k))
    sq = cv2.boxFilter(g * g, -1, (k, k))
    return np.sqrt(np.maximum(sq - mean * mean, 0))


def background_components(g):
    """Smooth regions touching the frame border = off-wafer background."""
    std = texture_std(g)
    smooth = (std < max(3.0, np.percentile(std, 20))).astype(np.uint8)
    smooth = cv2.morphologyEx(smooth, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    smooth = cv2.morphologyEx(smooth, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(smooth, 8)
    h, w = g.shape
    bg = np.zeros_like(smooth)
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        touches = (x <= 2 or y <= 2 or x + bw >= w - 2 or y + bh >= h - 2)
        if touches and area > 0.002 * h * w:
            bg[lbl == i] = 1
    return bg, std


def edge_fracs(bg):
    h, w = bg.shape
    b = max(3, int(0.02 * min(h, w)))
    return {"left": float(bg[:, :b].mean()), "right": float(bg[:, -b:].mean()),
            "top": float(bg[:b, :].mean()), "bottom": float(bg[-b:, :].mean())}


def main():
    for name, (path, anchors) in ra.SWEEPS.items():
        gray_ds, ds_scale, _ = mm.load_gray_downscaled(path)
        bg, std = background_components(gray_ds)
        ef = edge_fracs(bg)
        print(f"{name}: background edge-frac {{ {', '.join(f'{k}:{v:.3f}' for k,v in ef.items())} }}  "
              f"bg total {bg.mean():.3f}")
        fig, ax = plt.subplots(1, 3, figsize=(18, 5))
        ax[0].imshow(gray_ds, cmap="gray"); ax[0].set_title(f"{name} gray (original)")
        ax[1].imshow(std, cmap="viridis"); ax[1].set_title("local std (texture)")
        ax[2].imshow(gray_ds, cmap="gray")
        ax[2].imshow(np.ma.masked_where(bg == 0, bg), cmap="autumn", alpha=0.5)
        ax[2].set_title(f"background (border-touching smooth)  {ef}")
        fig.tight_layout(); fig.savefig(OUT / f"{name}_edgeseg.png", dpi=90); plt.close(fig)
        print(f"  saved {name}_edgeseg.png")


if __name__ == "__main__":
    main()
