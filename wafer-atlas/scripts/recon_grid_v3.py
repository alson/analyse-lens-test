"""V3 die-grid auto-detect via Hough line detection + projection profile.

Approach
--------
1. Silicon-bbox crop + downsample 4× (same as v2).
2. Canny edges within the silicon mask.
3. Probabilistic Hough → list of line segments. The wafer's scribe network
   produces TWO dominant angle clusters (~90° apart). Pick the two
   modal angles.
4. The rotation of the wafer is = (modal_angle_1) - 90° (taking the
   "near-horizontal" cluster as the reference).
5. Rotate the cropped image to axis-align the scribes.
6. **Column projection profile**: mean intensity per column. Local
   minima = vertical scribes. Spacing between minima = horizontal die
   pitch. Same for rows → vertical die pitch.
7. Lock grid origin from the first scribe minimum on each axis.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.ndimage import binary_opening, gaussian_filter
from scipy.signal import find_peaks
from skimage.feature import canny
from skimage.transform import probabilistic_hough_line, rotate


PHOTO_PATH = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-13/"
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S/f_8/step_0131_c.jpg"
)
OUT_DIR = Path(__file__).parent.parent / "out"
DOWN = 4


def _silicon_mask(rgb: np.ndarray) -> np.ndarray:
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    gray = 0.299 * R + 0.587 * G + 0.114 * B
    chroma_green = G - 0.5 * (R + B)
    sat = rgb.max(-1) - rgb.min(-1)
    mask = (chroma_green < 5.0) & (gray > 60.0) & ~((gray > 180.0) & (sat < 30.0))
    return binary_opening(mask, iterations=3)


def _bbox(mask: np.ndarray):
    ys, xs = np.where(mask)
    return ys.min(), ys.max(), xs.min(), xs.max()


def _downsample(arr: np.ndarray, factor: int) -> np.ndarray:
    h, w = arr.shape[:2]
    h_d, w_d = h // factor, w // factor
    arr = arr[:h_d * factor, :w_d * factor]
    if arr.ndim == 2:
        return arr.reshape(h_d, factor, w_d, factor).mean(axis=(1, 3))
    return arr.reshape(h_d, factor, w_d, factor, -1).mean(axis=(1, 3))


def main() -> int:
    rgb = np.asarray(Image.open(PHOTO_PATH).convert("RGB"), dtype=np.float32)
    mask = _silicon_mask(rgb)
    y0, y1, x0, x1 = _bbox(mask)
    rgb_crop = rgb[y0:y1, x0:x1]
    mask_crop = mask[y0:y1, x0:x1]
    rgb_ds = _downsample(rgb_crop, DOWN)
    mask_ds = _downsample(mask_crop.astype(np.float32), DOWN) > 0.5
    gray_ds = 0.299 * rgb_ds[..., 0] + 0.587 * rgb_ds[..., 1] + 0.114 * rgb_ds[..., 2]
    gray_ds = gray_ds.astype(np.float32)
    print(f"Crop shape (ds): {gray_ds.shape}, mask area={int(mask_ds.sum())}")

    # 1. Canny edge map on the masked region
    g = gray_ds.copy()
    g[~mask_ds] = g[mask_ds].mean()
    g_norm = g / 255.0
    edges = canny(g_norm, sigma=1.0, low_threshold=0.05, high_threshold=0.15)
    edges &= mask_ds  # constrain to silicon

    # 2. Probabilistic Hough — looser thresholds; many short fragments OK
    print(f"Edge pixels: {edges.sum()}")
    raw_lines = probabilistic_hough_line(
        edges, threshold=20, line_length=30, line_gap=12,
    )
    print(f"Hough lines detected: {len(raw_lines)}")

    # 3. Bin lines by angle (folded to [0, 180))
    angs, lengths = [], []
    for (x0_, y0_), (x1_, y1_) in raw_lines:
        ang = float(np.degrees(np.arctan2(y1_ - y0_, x1_ - x0_)) % 180.0)
        L = float(np.hypot(x1_ - x0_, y1_ - y0_))
        angs.append(ang)
        lengths.append(L)
    angs = np.asarray(angs)
    lengths = np.asarray(lengths)

    # Histogram weighted by length
    BIN = 2.0
    hist = np.zeros(int(180 / BIN))
    for a, L in zip(angs, lengths):
        hist[int(a / BIN) % len(hist)] += L
    # Smooth
    hist_sm = gaussian_filter(hist, sigma=1.0, mode="wrap")
    # Find the two dominant modes ~90° apart.
    primary_bin = int(hist_sm.argmax())
    primary_ang = (primary_bin + 0.5) * BIN
    # Search second peak among bins not within 30° of the primary
    sec_hist = hist_sm.copy()
    for b in range(len(hist_sm)):
        dist = min(abs(b - primary_bin), len(hist_sm) - abs(b - primary_bin)) * BIN
        if dist < 30 or dist > 150:
            sec_hist[b] = 0
    secondary_bin = int(sec_hist.argmax())
    secondary_ang = (secondary_bin + 0.5) * BIN
    print(f"Dominant Hough angles: primary {primary_ang:.1f}°, secondary {secondary_ang:.1f}°")

    # 4. Rotation = primary_ang - 90 if primary is closer to vertical (90°),
    # OR primary_ang - 0 if closer to horizontal (0°). Pick the one closer
    # to 0° or 90° based on which mode is which.
    # We'll align by rotating the image so the primary axis becomes purely
    # horizontal (0°) — interpret as "the scribes along the photo's wide
    # axis become exact rows".
    if abs(primary_ang - 90) < abs(primary_ang - 0) and abs(primary_ang - 90) < abs(primary_ang - 180):
        rotation = primary_ang - 90  # want it to be 90°
    else:
        rotation = primary_ang - 0  # want it to be 0°
        if rotation > 90:
            rotation -= 180
    print(f"Rotation to apply: {rotation:.2f}°")

    # 5. Rotate cropped image to align scribes with axes.
    gray_rot = rotate(gray_ds, rotation, resize=True, preserve_range=True,
                      mode="constant", cval=g[mask_ds].mean())
    mask_rot = rotate(mask_ds.astype(np.float32), rotation, resize=True,
                      preserve_range=True, order=0) > 0.5

    # 6. Projection profiles within any columns/rows that contain silicon.
    # Less strict than mask.mean > 0.5 — works for irregular fragments.
    col_valid = mask_rot.any(axis=0) & (mask_rot.sum(axis=0) > 50)
    row_valid = mask_rot.any(axis=1) & (mask_rot.sum(axis=1) > 50)
    # Mean of valid rows per column
    col_mean = np.array([
        gray_rot[mask_rot[:, c], c].mean() if mask_rot[:, c].any() else np.nan
        for c in range(gray_rot.shape[1])
    ])
    row_mean = np.array([
        gray_rot[r, mask_rot[r, :]].mean() if mask_rot[r, :].any() else np.nan
        for r in range(gray_rot.shape[0])
    ])

    # Restrict to the masked range
    col_valid_idx = np.where(col_valid)[0]
    row_valid_idx = np.where(row_valid)[0]
    if len(col_valid_idx) < 100 or len(row_valid_idx) < 100:
        print("Mask region too small after rotation")
        return 1
    cm = col_mean[col_valid_idx[0]:col_valid_idx[-1] + 1]
    rm = row_mean[row_valid_idx[0]:row_valid_idx[-1] + 1]
    # Detrend
    cm = cm - gaussian_filter(cm, sigma=30, mode="nearest")
    rm = rm - gaussian_filter(rm, sigma=30, mode="nearest")

    # Find local minima (scribes = dark lines → minima in projection)
    col_peaks, _ = find_peaks(-cm, distance=20, prominence=2.0)
    row_peaks, _ = find_peaks(-rm, distance=20, prominence=2.0)
    col_pitches = np.diff(col_peaks)
    row_pitches = np.diff(row_peaks)
    print(f"\nColumn scribes detected: {len(col_peaks)}  "
          f"(pitches: median {np.median(col_pitches):.1f} ds-px"
          f" = {np.median(col_pitches) * DOWN:.0f} full-px)")
    print(f"Row scribes detected: {len(row_peaks)}  "
          f"(pitches: median {np.median(row_pitches):.1f} ds-px"
          f" = {np.median(row_pitches) * DOWN:.0f} full-px)")
    print(f"\nCol pitches sample: {col_pitches[:20].tolist()}")
    print(f"Row pitches sample: {row_pitches[:10].tolist()}")

    # Save diagnostic
    fig, ax = plt.subplots(2, 2, figsize=(18, 12))
    ax[0, 0].imshow(gray_ds, cmap="gray")
    ax[0, 0].imshow(np.where(mask_ds, 0, 1), cmap="Reds", alpha=0.15)
    ax[0, 0].set_title(f"Silicon crop ds×{DOWN}")
    # Edge map
    ax[0, 1].imshow(edges, cmap="gray")
    ax[0, 1].set_title(f"Canny edges (silicon-masked) — {edges.sum()} px")
    # Rotated + scribe overlays
    ax[1, 0].imshow(gray_rot, cmap="gray")
    for c in col_peaks:
        ax[1, 0].axvline(col_valid_idx[0] + c, color="cyan", lw=0.5, alpha=0.7)
    for r in row_peaks:
        ax[1, 0].axhline(row_valid_idx[0] + r, color="orange", lw=0.5, alpha=0.7)
    ax[1, 0].set_title(f"Rotated {rotation:+.1f}° + detected scribes"
                       f" (col={len(col_peaks)} row={len(row_peaks)})")
    # Projection profiles
    ax[1, 1].plot(cm, label=f"Cols (detrended, {len(col_peaks)} scribes)", color="C0")
    ax[1, 1].plot(col_peaks, cm[col_peaks], "v", color="cyan")
    ax[1, 1].plot(rm + 30, label=f"Rows + 30 (detrended, {len(row_peaks)} scribes)",
                  color="C1")
    ax[1, 1].plot(row_peaks, rm[row_peaks] + 30, "v", color="orange")
    ax[1, 1].legend(loc="upper right")
    ax[1, 1].set_title("Projection profiles (scribe locations marked)")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "recon_grid_v3.png"
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
