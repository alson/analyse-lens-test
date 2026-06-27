"""Task #2 grounding: visualize, per registration sweep image, the silicon
(wafer) mask, the de-rotated image (via an EXPLICIT cv2 rotation matrix), and
the detected vertical/horizontal long-line scribe peaks. Lets us design the
whole-vs-jagged absolute anchoring against what's actually in frame.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.ndimage import sobel
from scipy.signal import find_peaks

# reuse anchor_fit for the ground-truth sweep image paths + anchors
_spec = importlib.util.spec_from_file_location(
    "anchor_fit", Path(__file__).parent / "anchor_fit_sweep.py")
af = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(af)

OUT = Path(__file__).parent.parent / "out" / "diag_2026_06"
OUT.mkdir(parents=True, exist_ok=True)
DOWNSAMPLE_W = 1024

SWEEPS = [
    ("sweep1_M0.385", af.__dict__),  # placeholder; we parse main() paths below
]


def load_gray_ds(path, target_width=DOWNSAMPLE_W):
    img = Image.open(path).convert("L")
    ratio = target_width / img.width
    img = img.resize((target_width, int(img.height * ratio)), Image.LANCZOS)
    return np.asarray(img, dtype=np.float32), ratio


def silicon_mask(gray_ds):
    """Binary mask of the wafer region. Background is dark AND smooth (low local
    texture); the wafer is highly textured. Threshold on local std, then keep the
    largest component and fill holes."""
    g = gray_ds.astype(np.float32)
    # local standard deviation (texture) over a window
    k = 15
    mean = cv2.boxFilter(g, -1, (k, k))
    sqmean = cv2.boxFilter(g * g, -1, (k, k))
    std = np.sqrt(np.maximum(sqmean - mean * mean, 0))
    # wafer = textured (high std) OR bright; background = dark + smooth
    textured = (std > max(4.0, np.percentile(std, 40))) | (g > np.percentile(g, 60))
    m = textured.astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((21, 21), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n <= 1:
        return m
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    mask = (lbl == big).astype(np.uint8)
    ff = mask.copy()
    h, w = mask.shape
    m2 = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ff, m2, (0, 0), 1)
    holes = (ff == 0).astype(np.uint8)
    return (mask | holes)


def detect_tilt(img, angle_range=8.0, bw=0.25, pct=80.0):
    sx = sobel(img, axis=1); sy = sobel(img, axis=0)
    mag = np.hypot(sx, sy)
    thr = np.percentile(mag, pct)
    strong = mag > thr
    ang = np.degrees(np.arctan2(sy[strong], sx[strong]))
    ang = (ang + 90) % 180 - 90
    bins = np.arange(-angle_range, angle_range + bw, bw)
    hist, _ = np.histogram(ang, bins=bins)
    centers = bins[:-1] + bw / 2
    hist[np.abs(centers) < bw] = 0
    return float(bins[hist.argmax()] + bw / 2)


def rot_matrix(shape, tilt_deg):
    h, w = shape
    return cv2.getRotationMatrix2D((w / 2, h / 2), -tilt_deg, 1.0)


def long_line_peaks(img_derot, mask_derot, axis, frac=0.40, pct=80.0, prom=0.12):
    """axis=0 -> vertical scribes (per-column counts); axis=1 -> horizontal."""
    work = img_derot if axis == 0 else img_derot.T
    m = mask_derot if axis == 0 else mask_derot.T
    edges = np.abs(sobel(work, axis=1))
    thr = np.percentile(edges[m > 0], pct) if (m > 0).any() else np.percentile(edges, pct)
    em = (edges > thr) & (m > 0)
    L = max(5, int(work.shape[0] * frac))
    from scipy.ndimage import binary_opening
    opened = binary_opening(em, structure=np.ones((L, 1), bool))
    sig = opened.sum(axis=0).astype(np.float32)
    if sig.max() <= 0:
        return np.array([], int), sig
    peaks, _ = find_peaks(sig / sig.max(), distance=12, prominence=prom)
    return peaks, sig


def explore(name, path, anchors):
    gray_ds, ratio = load_gray_ds(path)
    mask = silicon_mask(gray_ds)
    tilt = detect_tilt(gray_ds)
    M = rot_matrix(gray_ds.shape, tilt)
    h, w = gray_ds.shape
    derot = cv2.warpAffine(gray_ds, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    mask_d = cv2.warpAffine(mask.astype(np.float32), M, (w, h), flags=cv2.INTER_NEAREST)
    mask_d = (mask_d > 0.5).astype(np.uint8)
    cpx, csig = long_line_peaks(derot, mask_d, axis=0)
    rpy, rsig = long_line_peaks(derot, mask_d, axis=1)

    # per-edge silicon coverage in the de-rotated frame: a low value => that
    # wafer edge is in the FOV (background visible on that side).
    h2, w2 = mask_d.shape
    bw = int(0.08 * w2); bh = int(0.08 * h2)
    edge_cov = {
        "left": float(mask_d[:, :bw].mean()),
        "right": float(mask_d[:, -bw:].mean()),
        "top": float(mask_d[:bh, :].mean()),
        "bottom": float(mask_d[-bh:, :].mean()),
    }
    print(f"  edge silicon coverage (low=>edge visible): "
          + "  ".join(f"{k}={v:.2f}" for k, v in edge_cov.items()))

    # silicon horizontal extent (de-rotated): per-row and per-col coverage
    col_cov = mask_d.mean(axis=0)
    row_cov = mask_d.mean(axis=1)
    xfull = np.where(col_cov > 0.85)[0]
    yfull = np.where(row_cov > 0.85)[0]
    print(f"\n{name}: tilt={tilt:+.2f}°  {len(cpx)} vert scribes, {len(rpy)} horiz scribes")
    print(f"  silicon x-extent (any): {np.where(col_cov>0.05)[0][[0,-1]] if (col_cov>0.05).any() else '-'}"
          f"  full-height cols: {xfull[[0,-1]] if len(xfull) else 'none'}")
    print(f"  silicon y-extent (any): {np.where(row_cov>0.05)[0][[0,-1]] if (row_cov>0.05).any() else '-'}"
          f"  full-width rows: {yfull[[0,-1]] if len(yfull) else 'none'}")
    print(f"  vert scribe x (derot ds): {cpx.tolist()}")
    print(f"  horiz scribe y (derot ds): {rpy.tolist()}")

    fig, ax = plt.subplots(2, 2, figsize=(18, 12))
    ax[0, 0].imshow(gray_ds, cmap="gray"); ax[0, 0].set_title(f"{name} gray_ds")
    ax[0, 1].imshow(mask, cmap="gray"); ax[0, 1].set_title("silicon mask")
    ax[1, 0].imshow(derot, cmap="gray")
    for x in cpx:
        ax[1, 0].axvline(x, color="cyan", lw=0.8)
    for y in rpy:
        ax[1, 0].axhline(y, color="orange", lw=0.8)
    ax[1, 0].imshow(np.ma.masked_where(mask_d == 0, mask_d), alpha=0.12, cmap="autumn")
    ax[1, 0].set_title(f"de-rotated + scribes (tilt {tilt:+.2f}°)")
    ax[1, 1].plot(csig / max(csig.max(), 1), label="col(vert) sig")
    ax[1, 1].plot(col_cov, label="col silicon cov", alpha=0.6)
    for x in cpx:
        ax[1, 1].axvline(x, color="cyan", lw=0.6, ls=":")
    ax[1, 1].legend(fontsize=8); ax[1, 1].set_title("vertical-scribe signal + silicon coverage")
    fig.tight_layout()
    p = OUT / f"{name}_regexplore.png"
    fig.savefig(p, dpi=90); plt.close(fig)
    print(f"  saved {p}")


def main():
    import re
    src = (Path(__file__).parent / "anchor_fit_sweep.py").read_text()
    # pull the 4 (path, anchors) from anchor_fit main by executing a stripped copy
    # simpler: hardcode by re-reading af.main constants via regex is brittle; use known set
    sweeps = [
        ("sweep1_M0.385", af, "sweep1"),
    ]
    # Easiest: replicate the path/anchor tuples from af.main
    data = {
        "sweep1_M0.385": (
            "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
            "NIKKOR Z 100-400mm f_4.5-5.6 VR S/1_2.60/F11/"
            "00296|NIKKOR Z 100-400mm f_4.5-5.6 VR S|1_2.60|400.0 mm|F11|"
            "alm-20260208-221844-296.jpg",
            [(1, 1, 1827, 3548), (10, 1, 6078, 3901), (6, 5, 4341, 1853)]),
        "sweep2_M1.0": (
            "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
            "Nikon AF Micro-Nikkor 200mm f_4D IF-ED/1_1/F11/"
            "00353|Nikon AF Micro-Nikkor 200mm f_4D IF-ED|1_1|200.0 mm|F11|"
            "alm-20260129-162532-353.jpg",
            [(10, 2, 7136, 4742), (5, 2, 1012, 4243), (8, 5, 4831, 1009)]),
        "sweep3_M2.0": (
            "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
            "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001/2_1/F11/"
            "04069|Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001|2_1|"
            "300.0 mm|F11|alm-20260131-001833-1034.jpg",
            [(5, 4, 2094, 453), (5, 2, 1731, 5238), (7, 3, 6696, 3205)]),
        "sweep4_newer_rig": (
            "/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-12/"
            "NIKKOR Z 24-120mm f_4 S + 61mm extension (2026-05-08_201054)/"
            "f_11/step_0094_b.jpg",
            [(4, 2, 627, 4105), (8, 2, 6953, 4605), (6, 4, 4166, 1344)]),
    }
    for name, (path, anchors) in data.items():
        explore(name, path, anchors)


if __name__ == "__main__":
    main()
