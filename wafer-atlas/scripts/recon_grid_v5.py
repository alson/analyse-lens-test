"""V5 die-grid auto-detect: loose mask + projection-FFT + full-image overlay.

Combines v3's looser silicon mask (catches specular silicon spots) with
v4's robust FFT-based projection-profile pitch finding. Generates
scribes covering the whole image extent so the diagnostic overlay
spans the entire wafer fragment, not just the masked region.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.ndimage import binary_opening, gaussian_filter
from skimage.transform import rotate


PHOTO_PATH = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-13/"
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S/f_8/step_0131_c.jpg"
)
OUT_DIR = Path(__file__).parent.parent / "out"
DOWN = 4


def _silicon_mask(rgb: np.ndarray) -> np.ndarray:
    """v3's looser silicon mask — chromatic-only, captures specular spots."""
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


def _fft_pitch_and_phase(profile: np.ndarray, min_pitch: float, max_pitch: float
                         ) -> tuple[float, float, np.ndarray, np.ndarray]:
    p = profile - np.nanmean(profile)
    p = np.nan_to_num(p)
    N = p.size
    p = p * np.hanning(N)
    F = np.fft.rfft(p)
    freqs = np.fft.rfftfreq(N, d=1.0)
    mag = np.abs(F)
    f_min = 1.0 / max_pitch
    f_max = 1.0 / min_pitch
    band = (freqs >= f_min) & (freqs <= f_max)
    if not band.any():
        return float("nan"), float("nan"), freqs, mag
    band_idx = np.where(band)[0]
    best_idx = band_idx[mag[band_idx].argmax()]
    pitch = 1.0 / freqs[best_idx] if freqs[best_idx] > 0 else float("nan")
    phase = float(np.angle(F[best_idx]))
    return pitch, phase, freqs, mag


def main() -> int:
    rgb = np.asarray(Image.open(PHOTO_PATH).convert("RGB"), dtype=np.float32)
    mask = _silicon_mask(rgb)
    print(f"Silicon mask area (full-res px): {int(mask.sum())} "
          f"({100 * mask.mean():.1f}% of frame)")
    y0, y1, x0, x1 = _bbox(mask)
    print(f"Silicon bbox: y={y0}..{y1} x={x0}..{x1}  ({y1 - y0}×{x1 - x0})")
    rgb_crop = rgb[y0:y1, x0:x1]
    mask_crop = mask[y0:y1, x0:x1]
    rgb_ds = _downsample(rgb_crop, DOWN)
    mask_ds = _downsample(mask_crop.astype(np.float32), DOWN) > 0.5
    gray_ds = 0.299 * rgb_ds[..., 0] + 0.587 * rgb_ds[..., 1] + 0.114 * rgb_ds[..., 2]
    gray_ds = gray_ds.astype(np.float32)
    print(f"DS shape: {gray_ds.shape}, mask area={int(mask_ds.sum())}")

    rotation = 1.0
    gray_rot = rotate(gray_ds, rotation, resize=False, preserve_range=True,
                      mode="constant", cval=gray_ds[mask_ds].mean())
    mask_rot = rotate(mask_ds.astype(np.float32), rotation, resize=False,
                      preserve_range=True, order=0) > 0.5

    H, W = gray_rot.shape

    # Column / row projection: only count silicon-masked pixels per col/row
    col_sum = np.where(mask_rot, gray_rot, 0).sum(axis=0)
    col_cnt = mask_rot.sum(axis=0)
    col_mean = np.where(col_cnt >= 50, col_sum / np.maximum(col_cnt, 1), np.nan)
    row_sum = np.where(mask_rot, gray_rot, 0).sum(axis=1)
    row_cnt = mask_rot.sum(axis=1)
    row_mean = np.where(row_cnt >= 50, row_sum / np.maximum(row_cnt, 1), np.nan)

    # Find valid range; replace internal NaN with local mean
    c_valid = ~np.isnan(col_mean)
    r_valid = ~np.isnan(row_mean)
    c_idx0, c_idx1 = np.where(c_valid)[0][[0, -1]]
    r_idx0, r_idx1 = np.where(r_valid)[0][[0, -1]]
    cm = col_mean[c_idx0:c_idx1 + 1]
    rm = row_mean[r_idx0:r_idx1 + 1]
    cm = np.where(np.isnan(cm), np.nanmean(cm), cm)
    rm = np.where(np.isnan(rm), np.nanmean(rm), rm)
    # Detrend
    cm = cm - gaussian_filter(cm, sigma=80, mode="nearest")
    rm = rm - gaussian_filter(rm, sigma=80, mode="nearest")

    # Search ranges:
    # User said 9-10 dies horizontally in ~6650 full-px → ~165-180 ds-px
    h_pitch_ds, h_phase, h_freqs, h_mag = _fft_pitch_and_phase(cm, 130, 220)
    # Vertically: user said 4 full dies + partials = ~6 total in ~3900 full-px
    #             → ~163 ds-px. If dies are square, expect ~h_pitch_ds.
    v_pitch_ds, v_phase, v_freqs, v_mag = _fft_pitch_and_phase(rm, 130, 220)

    h_pitch_full = h_pitch_ds * DOWN
    v_pitch_full = v_pitch_ds * DOWN
    print(f"\nHorizontal die pitch: {h_pitch_ds:.2f} ds-px = {h_pitch_full:.1f} full-px")
    print(f"Vertical die pitch:   {v_pitch_ds:.2f} ds-px = {v_pitch_full:.1f} full-px")
    print(f"  dies across silicon bbox: {(x1 - x0) / h_pitch_full:.2f}")
    print(f"  dies tall across silicon bbox: {(y1 - y0) / v_pitch_full:.2f}")

    # Origin from phase (sub-pixel scribe location, modulo pitch)
    h_freq = 1.0 / h_pitch_ds
    v_freq = 1.0 / v_pitch_ds
    h_offset_ds = (-h_phase / (2 * np.pi * h_freq)) % h_pitch_ds
    v_offset_ds = (-v_phase / (2 * np.pi * v_freq)) % v_pitch_ds
    print(f"\nGrid origin (sub-pixel offset within first valid range):")
    print(f"  vertical scribe offset = {h_offset_ds:.2f} ds-px from x={c_idx0}")
    print(f"  horizontal scribe offset = {v_offset_ds:.2f} ds-px from y={r_idx0}")

    # Generate scribes covering the WHOLE rotated image extent (not just bbox)
    first_v = c_idx0 + h_offset_ds
    first_h = r_idx0 + v_offset_ds
    # Walk left and right from first_v until past image bounds
    col_scribes_ds = []
    x = first_v
    while x >= -h_pitch_ds:
        col_scribes_ds.append(x)
        x -= h_pitch_ds
    x = first_v + h_pitch_ds
    while x <= W + h_pitch_ds:
        col_scribes_ds.append(x)
        x += h_pitch_ds
    col_scribes_ds.sort()
    row_scribes_ds = []
    y = first_h
    while y >= -v_pitch_ds:
        row_scribes_ds.append(y)
        y -= v_pitch_ds
    y = first_h + v_pitch_ds
    while y <= H + v_pitch_ds:
        row_scribes_ds.append(y)
        y += v_pitch_ds
    row_scribes_ds.sort()
    print(f"\nGenerated {len(col_scribes_ds)} vertical scribes,"
          f" {len(row_scribes_ds)} horizontal scribes covering rotated image")

    # Diagnostic
    fig, ax = plt.subplots(2, 2, figsize=(18, 12))
    ax[0, 0].imshow(gray_rot, cmap="gray")
    ax[0, 0].imshow(np.where(mask_rot, 0, 1), cmap="Reds", alpha=0.10)
    for x in col_scribes_ds:
        ax[0, 0].axvline(x, color="cyan", lw=0.8, alpha=0.7)
    for y in row_scribes_ds:
        ax[0, 0].axhline(y, color="orange", lw=0.8, alpha=0.7)
    ax[0, 0].set_xlim(0, W)
    ax[0, 0].set_ylim(H, 0)
    ax[0, 0].set_title(f"Predicted die grid: h={h_pitch_full:.0f}px, v={v_pitch_full:.0f}px"
                       f" ({len(col_scribes_ds)}V × {len(row_scribes_ds)}H scribes)")
    ax[0, 1].plot(cm, color="C0", lw=0.7)
    for x in col_scribes_ds:
        x_local = x - c_idx0
        if 0 <= x_local < len(cm):
            ax[0, 1].axvline(x_local, color="cyan", lw=0.4, alpha=0.4)
    ax[0, 1].set_title(f"Column projection (detrended); h_pitch={h_pitch_ds:.1f} ds-px")
    ax[1, 0].plot(rm, color="C1", lw=0.7)
    for y in row_scribes_ds:
        y_local = y - r_idx0
        if 0 <= y_local < len(rm):
            ax[1, 0].axvline(y_local, color="orange", lw=0.4, alpha=0.4)
    ax[1, 0].set_title(f"Row projection (detrended); v_pitch={v_pitch_ds:.1f} ds-px")
    ax[1, 1].plot(1 / np.maximum(h_freqs[1:], 1e-6), h_mag[1:], color="C0", label="cols")
    ax[1, 1].plot(1 / np.maximum(v_freqs[1:], 1e-6), v_mag[1:], color="C1", label="rows")
    ax[1, 1].axvline(h_pitch_ds, color="C0", lw=0.5, ls="--")
    ax[1, 1].axvline(v_pitch_ds, color="C1", lw=0.5, ls="--")
    ax[1, 1].set_xlim(0, 400)
    ax[1, 1].set_xlabel("pitch (ds-px)")
    ax[1, 1].set_title("Projection-FFT magnitude vs pitch")
    ax[1, 1].legend()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "recon_grid_v5.png"
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
