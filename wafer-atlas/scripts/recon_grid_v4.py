"""V4: FFT of projection profile → robust die pitch.

V3 used find_peaks on the projection profile with low prominence, which
over-counted sub-die features as scribes. V4 takes the FFT of the 1-D
projection profile and reads the dominant frequency directly. Robust
against (a) noisy mask boundaries leaking in non-silicon content,
(b) sub-die periodicities competing with die-pitch periodicities,
because the die-pitch fundamental is the strongest peak in the 1-D
spectrum of the projection.

Then the grid origin is locked by finding the phase of the FFT
fundamental — same trick as locating maze-grid lattice offset in
methods/maze_fft.py.
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
    """Tighter silicon mask: warm-tan + not bright-achromatic."""
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    gray = 0.299 * R + 0.587 * G + 0.114 * B
    chroma_green = G - 0.5 * (R + B)
    sat = rgb.max(-1) - rgb.min(-1)
    # Silicon: warm (R-B > 20), not green, not too bright achromatic
    silicon = (
        (R - B > 15)  # warm tan
        & (chroma_green < 5.0)  # not green background
        & (gray > 60.0)
        & (gray < 200.0)
        & ~((gray > 180.0) & (sat < 30.0))  # not metal mount
    )
    silicon = binary_opening(silicon, iterations=4)
    return silicon


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
    """Return (pitch_in_samples, phase_at_pitch, freqs, mag)."""
    p = profile - np.nanmean(profile)
    p = np.nan_to_num(p)
    N = p.size
    # Hann window
    p = p * np.hanning(N)
    F = np.fft.rfft(p)
    freqs = np.fft.rfftfreq(N, d=1.0)  # cycles/sample
    mag = np.abs(F)
    # Search in the pitch band
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
    print(f"Silicon bbox: y={y0}..{y1} x={x0}..{x1}"
          f"  ({y1 - y0}×{x1 - x0})")
    rgb_crop = rgb[y0:y1, x0:x1]
    mask_crop = mask[y0:y1, x0:x1]
    rgb_ds = _downsample(rgb_crop, DOWN)
    mask_ds = _downsample(mask_crop.astype(np.float32), DOWN) > 0.5
    gray_ds = 0.299 * rgb_ds[..., 0] + 0.587 * rgb_ds[..., 1] + 0.114 * rgb_ds[..., 2]
    gray_ds = gray_ds.astype(np.float32)
    print(f"DS shape: {gray_ds.shape}, mask area={int(mask_ds.sum())}")

    # Apply ~1° rotation found by v3
    rotation = 1.0
    gray_rot = rotate(gray_ds, rotation, resize=False, preserve_range=True,
                      mode="constant", cval=gray_ds[mask_ds].mean())
    mask_rot = rotate(mask_ds.astype(np.float32), rotation, resize=False,
                      preserve_range=True, order=0) > 0.5

    # Projection profile (only over silicon-masked rows/cols per axis)
    col_mean = np.array([
        gray_rot[mask_rot[:, c], c].mean() if mask_rot[:, c].sum() > 50 else np.nan
        for c in range(gray_rot.shape[1])
    ])
    row_mean = np.array([
        gray_rot[r, mask_rot[r, :]].mean() if mask_rot[r, :].sum() > 50 else np.nan
        for r in range(gray_rot.shape[0])
    ])
    # Restrict to ranges with values
    col_valid = ~np.isnan(col_mean)
    row_valid = ~np.isnan(row_mean)
    if col_valid.sum() < 100 or row_valid.sum() < 100:
        print("Profile too short")
        return 1
    c_idx = np.where(col_valid)[0]
    r_idx = np.where(row_valid)[0]
    cm = col_mean[c_idx[0]:c_idx[-1] + 1]
    rm = row_mean[r_idx[0]:r_idx[-1] + 1]
    # Fill any inner NaNs
    cm = np.where(np.isnan(cm), np.nanmean(cm), cm)
    rm = np.where(np.isnan(rm), np.nanmean(rm), rm)
    # Detrend (subtract a smooth running mean)
    cm = cm - gaussian_filter(cm, sigma=80, mode="nearest")
    rm = rm - gaussian_filter(rm, sigma=80, mode="nearest")

    # User said ~9-10 dies across ~6652 px → die ~665 px ≈ 166 ds-px.
    # Search 100..250 ds-px for the horizontal die pitch.
    h_pitch_ds, h_phase, h_freqs, h_mag = _fft_pitch_and_phase(cm, 100, 250)
    # Vertical: ~4-5 rows of full dies + partials at top and bottom.
    # If 5 full rows including partials in 3918 px → ~780 px ≈ 195 ds-px.
    v_pitch_ds, v_phase, v_freqs, v_mag = _fft_pitch_and_phase(rm, 130, 280)

    print(f"\nHorizontal die pitch: {h_pitch_ds:.2f} ds-px "
          f"= {h_pitch_ds * DOWN:.1f} full-px"
          f"  → {(c_idx[-1] - c_idx[0]) / h_pitch_ds:.2f} dies across silicon")
    print(f"Vertical die pitch:   {v_pitch_ds:.2f} ds-px "
          f"= {v_pitch_ds * DOWN:.1f} full-px"
          f"  → {(r_idx[-1] - r_idx[0]) / v_pitch_ds:.2f} dies tall")

    # Origin (sub-pixel): phase of the fundamental.
    # A scribe (dark line) is a -cos(2π f x + phase) trough; trough at
    # x_offset = -phase / (2π f).
    h_freq = 1.0 / h_pitch_ds
    v_freq = 1.0 / v_pitch_ds
    h_offset_ds = (-h_phase / (2 * np.pi * h_freq)) % h_pitch_ds
    v_offset_ds = (-v_phase / (2 * np.pi * v_freq)) % v_pitch_ds
    print(f"\nFirst vertical scribe at col = {c_idx[0] + h_offset_ds:.2f} ds-px"
          f" ({(c_idx[0] + h_offset_ds) * DOWN:.0f} full-px) from crop x0")
    print(f"First horizontal scribe at row = {r_idx[0] + v_offset_ds:.2f} ds-px"
          f" ({(r_idx[0] + v_offset_ds) * DOWN:.0f} full-px) from crop y0")

    # Build the full die-grid line list
    h_n = int((c_idx[-1] - c_idx[0]) / h_pitch_ds) + 2
    v_n = int((r_idx[-1] - r_idx[0]) / v_pitch_ds) + 2
    col_scribes_ds = [c_idx[0] + h_offset_ds + k * h_pitch_ds for k in range(-1, h_n + 1)]
    row_scribes_ds = [r_idx[0] + v_offset_ds + k * v_pitch_ds for k in range(-1, v_n + 1)]
    # Keep only those inside or near the silicon bbox
    col_scribes_ds = [x for x in col_scribes_ds if -h_pitch_ds < x < gray_rot.shape[1] + h_pitch_ds]
    row_scribes_ds = [y for y in row_scribes_ds if -v_pitch_ds < y < gray_rot.shape[0] + v_pitch_ds]
    print(f"\nPredicted grid: {len(col_scribes_ds)} vertical scribes,"
          f" {len(row_scribes_ds)} horizontal scribes")

    # Diagnostic
    fig, ax = plt.subplots(2, 2, figsize=(18, 12))
    ax[0, 0].imshow(gray_rot, cmap="gray")
    ax[0, 0].imshow(np.where(mask_rot, 0, 1), cmap="Reds", alpha=0.15)
    for x in col_scribes_ds:
        ax[0, 0].axvline(x, color="cyan", lw=0.8, alpha=0.7)
    for y in row_scribes_ds:
        ax[0, 0].axhline(y, color="orange", lw=0.8, alpha=0.7)
    ax[0, 0].set_title(f"Rotated +1° + predicted die grid"
                       f" (h_pitch={h_pitch_ds:.1f}, v_pitch={v_pitch_ds:.1f}) ds-px")
    ax[0, 1].plot(cm, color="C0")
    ax[0, 1].set_title(f"Column projection (detrended), h_pitch={h_pitch_ds:.1f}")
    for x in col_scribes_ds:
        x_local = x - c_idx[0]
        if 0 <= x_local < len(cm):
            ax[0, 1].axvline(x_local, color="cyan", lw=0.5, alpha=0.5)
    ax[1, 0].plot(rm, color="C1")
    ax[1, 0].set_title(f"Row projection (detrended), v_pitch={v_pitch_ds:.1f}")
    for y in row_scribes_ds:
        y_local = y - r_idx[0]
        if 0 <= y_local < len(rm):
            ax[1, 0].axvline(y_local, color="orange", lw=0.5, alpha=0.5)
    # FFT magnitudes
    ax[1, 1].plot(1 / np.maximum(h_freqs[1:], 1e-6), h_mag[1:], color="C0", label="cols")
    ax[1, 1].plot(1 / np.maximum(v_freqs[1:], 1e-6), v_mag[1:], color="C1", label="rows")
    ax[1, 1].axvline(h_pitch_ds, color="C0", lw=0.5, ls="--")
    ax[1, 1].axvline(v_pitch_ds, color="C1", lw=0.5, ls="--")
    ax[1, 1].set_xlim(0, 400)
    ax[1, 1].set_xlabel("pitch (ds-px)")
    ax[1, 1].set_title("Projection-FFT magnitude vs pitch")
    ax[1, 1].legend()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "recon_grid_v4.png"
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
