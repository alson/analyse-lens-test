"""Task #1: test the field-curvature explanation for sweep2's gap with ONE
consistent pipeline. Compute a non-saturating focus metric (Laplacian variance
+ Tenengrad) on fixed boxes at several field positions (image centre + the two
4D-bar instances + left/right/centre probe boxes), and report each box's focus
argmax. If best-focus shot varies smoothly with field x-position, the gap is
field curvature, not a measurement artifact.

Usage: diag_field_curvature.py <sweep_name>
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

_spec = importlib.util.spec_from_file_location(
    "diag_measure", Path(__file__).parent / "diag_measure.py")
dm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dm)

A = Path(__file__).parent.parent
OUT = A / "out" / "diag_2026_06"
IMAGE_W, IMAGE_H = 8256, 5504


def focus_metrics(box):
    b = box.astype(np.float32)
    gx = cv2.Sobel(b, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(b, cv2.CV_32F, 0, 1, ksize=3)
    return float((gx * gx + gy * gy).mean()), float(cv2.Laplacian(b, cv2.CV_32F).var())


def main():
    name = sys.argv[1]
    cfg = {c["name"]: c for c in dm.task15.SWEEPS}[name]
    aff = dm.anchors[name]
    shots = sorted(cfg["dir"].glob("*.jpg")) + sorted(cfg["dir"].glob("*.JPG"))

    # probe boxes: centre, and 5 across the horizontal mid-line
    half = 350
    probes = {}
    for frac, tag in [(0.18, "x_left"), (0.34, "x_midleft"), (0.5, "x_centre"),
                      (0.66, "x_midright"), (0.82, "x_right")]:
        cx = int(frac * IMAGE_W)
        probes[tag] = (cx, IMAGE_H // 2)
    # also the actual 4D-bar instance centres
    for col in (0, 4, 8):
        geo = dm.instance_geometry(aff, col)
        if 0 < geo["cx"] < IMAGE_W and 0 < geo["cy"] < IMAGE_H:
            probes[f"bar{col}D"] = (int(geo["cx"]), int(geo["cy"]))

    curves = {k: [] for k in probes}
    for sp in shots:
        img = np.asarray(Image.open(sp).convert("L"))
        for tag, (cx, cy) in probes.items():
            y0, y1 = max(0, cy - half), min(img.shape[0], cy + half)
            x0, x1 = max(0, cx - half), min(img.shape[1], cx + half)
            box = img[y0:y1, x0:x1]
            _, lv = focus_metrics(box)
            curves[tag].append(lv)

    ref = cfg.get("lsf_ref_shot")
    print(f"{name}  ref(centre)={ref}  n_shots={len(shots)}")
    print(f"{'probe':12s} {'x_px':>7s} {'focus_shot(lapvar)':>18s}")
    rows = []
    for tag, (cx, cy) in probes.items():
        arr = np.array(curves[tag], float)
        am = int(np.nanargmax(arr))
        rows.append((tag, cx, am))
        print(f"{tag:12s} {cx:7d} {am:18d}")

    fig, ax = plt.subplots(figsize=(13, 6))
    for tag in probes:
        arr = np.array(curves[tag], float)
        ax.plot(arr / np.nanmax(arr), lw=1.3, label=f"{tag} (peak {int(np.nanargmax(arr))})")
    if ref is not None:
        ax.axvline(ref, color="k", ls="--", alpha=0.6, label=f"centre LSF ref {ref}")
    ax.set_title(f"{name} — Laplacian-variance focus vs field position")
    ax.set_xlabel("shot"); ax.set_ylabel("lapvar / max"); ax.grid(alpha=0.3)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    p = OUT / f"{name}_field_curvature.png"
    fig.savefig(p, dpi=120); plt.close(fig)
    print(f"saved {p}")
    json.dump(rows, open(OUT / f"{name}_field_curvature.json", "w"), indent=1)


if __name__ == "__main__":
    main()
