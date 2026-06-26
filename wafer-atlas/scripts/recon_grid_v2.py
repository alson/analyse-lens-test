"""V2 of die-grid auto-detect: tight-crop to silicon, downsample, then FFT.

Changes from v1:
- Bounding box of silicon mask → tight crop.
- 4× downsample so the die fundamental lands at a useful FFT radius.
- DC-suppression is radius-aware (4 px on the downsampled image).
- Looks for the die fundamental in the 5-50 cycle band specifically,
  which matches ~10 dies across an ~3000-px tight crop downsampled 4×
  (~750 px → die pitch ~75 px → FFT radius ~10).
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.ndimage import binary_opening, gaussian_filter


PHOTO_PATH = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-13/"
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S/f_8/step_0131_c.jpg"
)
OUT_DIR = Path(__file__).parent.parent / "out"


def _silicon_mask(rgb: np.ndarray) -> np.ndarray:
    """True on silicon, False on background/mount."""
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    gray = 0.299 * R + 0.587 * G + 0.114 * B
    chroma_green = G - 0.5 * (R + B)
    sat = rgb.max(-1) - rgb.min(-1)
    mask = (chroma_green < 5.0) & (gray > 60.0) & ~((gray > 180.0) & (sat < 30.0))
    return binary_opening(mask, iterations=3)


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(mask)
    return ys.min(), ys.max(), xs.min(), xs.max()


def _downsample_box(arr: np.ndarray, factor: int) -> np.ndarray:
    h, w = arr.shape[:2]
    h_d, w_d = h // factor, w // factor
    arr = arr[:h_d * factor, :w_d * factor]
    if arr.ndim == 2:
        return arr.reshape(h_d, factor, w_d, factor).mean(axis=(1, 3))
    return arr.reshape(h_d, factor, w_d, factor, -1).mean(axis=(1, 3))


def main() -> int:
    rgb = np.asarray(Image.open(PHOTO_PATH).convert("RGB"), dtype=np.float32)
    print(f"Photo full shape: {rgb.shape}")
    mask = _silicon_mask(rgb)
    y0, y1, x0, x1 = _bbox(mask)
    print(f"Silicon bbox in full photo: y={y0}..{y1}  x={x0}..{x1}"
          f"  ({y1 - y0}×{x1 - x0})")
    rgb_crop = rgb[y0:y1, x0:x1]
    mask_crop = mask[y0:y1, x0:x1]

    DOWN = 4
    rgb_ds = _downsample_box(rgb_crop, DOWN)
    mask_ds = _downsample_box(mask_crop.astype(np.float32), DOWN) > 0.5
    gray_ds = (0.299 * rgb_ds[..., 0] + 0.587 * rgb_ds[..., 1] + 0.114 * rgb_ds[..., 2])
    print(f"Downsampled crop shape: {gray_ds.shape}  (mask area {mask_ds.sum():.0f})")

    # Fill background with neutral grey + Hann window
    work = gray_ds.copy()
    work[~mask_ds] = gray_ds[mask_ds].mean()
    work -= work.mean()
    h, w = work.shape
    han = np.outer(np.hanning(h), np.hanning(w)).astype(np.float32)
    work *= han

    F = np.fft.fftshift(np.fft.fft2(work))
    mag = np.abs(F).astype(np.float32)
    cy, cx = h // 2, w // 2
    rr = np.indices(mag.shape)
    r = np.sqrt((rr[0] - cy) ** 2 + (rr[1] - cx) ** 2)
    # Aggressive DC suppression: zero out r < 4.
    mag_hi = mag.copy()
    mag_hi[r < 4] = 0
    # Light smoothing to consolidate broad peaks.
    mag_sm = gaussian_filter(mag_hi, sigma=1.2)

    # Pull top-30 peaks (non-max suppress each by 6-px radius)
    peaks = []
    work_arr = mag_sm.copy()
    for _ in range(30):
        idx = np.unravel_index(work_arr.argmax(), work_arr.shape)
        if work_arr[idx] <= 0:
            break
        py, px = idx
        peaks.append({
            "py": int(py), "px": int(px),
            "dy": int(py - cy), "dx": int(px - cx),
            "r": float(np.hypot(py - cy, px - cx)),
            "ang": float(np.degrees(np.arctan2(py - cy, px - cx)) % 180.0),
            "amp": float(mag_sm[py, px]),
        })
        ry = slice(max(0, py - 6), min(h, py + 7))
        rx = slice(max(0, px - 6), min(w, px + 7))
        work_arr[ry, rx] = 0

    print("\nTop 30 peaks (downsampled FFT, DC-suppressed):")
    print(f"  {'idx':>3} {'dy':>5} {'dx':>5} {'r':>6} {'ang°':>7} {'amp':>10}")
    for i, p in enumerate(peaks):
        # Pitch in original-photo pixels:
        # downsampled FFT freq = r / max(h, w)  cycles/px-downsampled
        # original pitch = pitch_ds * DOWN = (max(h, w) / r) * DOWN
        pitch_px_orig = (max(h, w) / p["r"]) * DOWN if p["r"] > 0 else float("inf")
        print(f"  {i:3d} {p['dy']:+5d} {p['dx']:+5d} {p['r']:6.2f}"
              f" {p['ang']:7.2f} {p['amp']:.3e}  pitch≈{pitch_px_orig:6.1f}px")

    # Save diagnostic
    fig, ax = plt.subplots(1, 2, figsize=(18, 8))
    ax[0].imshow(gray_ds, cmap="gray")
    ax[0].imshow(np.where(mask_ds, 0, 1), cmap="Reds", alpha=0.15)
    ax[0].set_title(f"Silicon crop (downsampled {DOWN}×) — {gray_ds.shape}")
    # FFT zoom ±60 px around centre
    half = min(80, cy, cx)
    log_mag = np.log10(mag_sm[cy - half:cy + half, cx - half:cx + half] + 1)
    im1 = ax[1].imshow(log_mag, cmap="viridis")
    for i, p in enumerate(peaks[:12]):
        cy_p = p["py"] - (cy - half)
        cx_p = p["px"] - (cx - half)
        ax[1].add_patch(plt.Circle((cx_p, cy_p), 4, fill=False,
                                    color="red", lw=1.5))
        ax[1].annotate(str(i), (cx_p, cy_p), color="white", fontsize=8)
    ax[1].set_title("FFT log-magnitude zoom (top 12 peaks)")
    plt.colorbar(im1, ax=ax[1], fraction=0.046, pad=0.04)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    diag_path = OUT_DIR / "recon_grid_v2.png"
    fig.tight_layout()
    fig.savefig(diag_path, dpi=110)
    plt.close(fig)
    print(f"\nSaved: {diag_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
