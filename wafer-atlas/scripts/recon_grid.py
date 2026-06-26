"""Auto-detect die grid + super-cell pitch from a wafer overview photo.

Approach
--------
1. Load step_0131_c.jpg as grayscale; isolate the wafer-fragment region
   by Otsu-threshold on saturation/brightness (the green background is
   chromatically distinct from the silicon).
2. Cosine-window the masked region; 2D FFT magnitude.
3. The die-grid produces a periodic structure with peaks on a pair of
   orthogonal axes (the scribe directions). Find the dominant non-DC
   peak; that's the die fundamental. Its angle gives the in-image
   rotation of the wafer.
4. Sub-harmonic peaks at die_freq / N (N=2,3,4) reveal the super-cell
   periodicity. The strongest sub-harmonic wins.
5. Save a side-by-side diagnostic PNG: original + FFT magnitude (zoomed)
   with detected peaks circled.

This is reconnaissance — no atlas YAML is produced yet.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter


PHOTO_PATH = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-13/"
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S/f_8/step_0131_c.jpg"
)
OUT_DIR = Path(__file__).parent.parent / "out"


def _load_gray_and_mask() -> tuple[np.ndarray, np.ndarray]:
    """Return (gray_float32, mask_bool) where mask is True on the silicon."""
    rgb = np.asarray(Image.open(PHOTO_PATH).convert("RGB"), dtype=np.float32)
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    gray = (0.299 * R + 0.587 * G + 0.114 * B)
    # Silicon is yellow-ish-grey (R≈G>B). Background is green (G > R).
    # Mask = where green isn't the dominant channel.
    chroma_green = G - 0.5 * (R + B)
    mask = (chroma_green < 5.0) & (gray > 60.0)
    # Erode to drop edge artefacts and the metal mount specular reflection
    # at the bottom (mount is bright + colourless).
    from scipy.ndimage import binary_erosion, binary_opening
    mask = binary_opening(mask, iterations=2)
    # Drop the bright metal mount: bright (>200) AND no chroma variation.
    saturation = rgb.max(axis=-1) - rgb.min(axis=-1)
    mount = (gray > 180.0) & (saturation < 30.0)
    mask = mask & ~mount
    return gray, mask


def _fft_diagnostic(gray: np.ndarray, mask: np.ndarray) -> dict:
    """Compute the 2D FFT of the masked region and find the die-grid peaks."""
    h, w = gray.shape
    work = gray.copy()
    work[~mask] = gray[mask].mean()  # fill background with neutral grey
    work -= work.mean()
    # Cosine window to suppress edge ringing
    yy, xx = np.meshgrid(
        np.hanning(h).astype(np.float32),
        np.hanning(w).astype(np.float32),
        indexing="ij",
    )
    work *= yy * xx
    F = np.fft.fftshift(np.fft.fft2(work))
    mag = np.abs(F)
    # Suppress DC and immediate neighbours (low-freq trend).
    cy, cx = h // 2, w // 2
    rr, cc = np.indices(mag.shape)
    r2 = (rr - cy) ** 2 + (cc - cx) ** 2
    mag_hi = mag.copy()
    mag_hi[r2 < 25] = 0  # zero out DC + ±5px
    # Light smoothing to consolidate peaks
    mag_sm = gaussian_filter(mag_hi, sigma=1.5)

    # Find top N peaks in mag_sm (non-DC).
    peaks = []
    work_arr = mag_sm.copy()
    for _ in range(20):
        idx = np.unravel_index(work_arr.argmax(), work_arr.shape)
        if work_arr[idx] <= 0:
            break
        peaks.append(idx)
        # Suppress a region around this peak so we get distinct ones.
        py, px = idx
        ry = np.clip([py - 6, py + 7], 0, h)
        rx = np.clip([px - 6, px + 7], 0, w)
        work_arr[ry[0]:ry[1], rx[0]:rx[1]] = 0

    return {
        "mag": mag,
        "mag_sm": mag_sm,
        "peaks": peaks,
        "centre": (cy, cx),
        "shape": (h, w),
        "mask_area_px": int(mask.sum()),
    }


def _peaks_to_axes(diag: dict) -> dict:
    """Classify peaks into two orthogonal axes and report pitches.

    Returns:
        primary_axis_angle_deg: angle of strongest peak axis from +x
        die_pitch_axis1_px / die_pitch_axis2_px: pitch in original-image px
        subharmonic_at_axis: dict of N -> dict(amp, expected_radius)
    """
    cy, cx = diag["centre"]
    h, w = diag["shape"]
    peaks = diag["peaks"]
    mag = diag["mag_sm"]

    # Compute (dy, dx) from centre, radius, angle for each peak
    p_info = []
    for py, px in peaks:
        dy, dx = py - cy, px - cx
        r = float(np.hypot(dy, dx))
        ang = float(np.degrees(np.arctan2(dy, dx)) % 180.0)
        p_info.append({"py": py, "px": px, "dy": dy, "dx": dx,
                       "r": r, "ang_deg": ang, "amp": float(mag[py, px])})
    # Sort by amplitude
    p_info.sort(key=lambda p: -p["amp"])

    # Highest-amplitude peak determines the primary axis.
    if not p_info:
        return {"error": "no peaks"}
    p0 = p_info[0]
    ang0 = p0["ang_deg"]
    r0 = p0["r"]

    # Group peaks by angle proximity (within 8°), fold to [0,180)
    def near_angle(a, b, tol=8.0):
        d = abs((a - b) % 180.0)
        return min(d, 180 - d) < tol

    axis1_peaks = [p for p in p_info if near_angle(p["ang_deg"], ang0)]
    other_peaks = [p for p in p_info if not near_angle(p["ang_deg"], ang0)]
    # axis2 is orthogonal: angle near ang0 + 90
    ang90 = (ang0 + 90) % 180
    axis2_peaks = [p for p in other_peaks if near_angle(p["ang_deg"], ang90)]

    # Die fundamental = strongest peak on each axis.
    def pitch_from(peaks_list, h, w):
        if not peaks_list:
            return None
        # Strongest peak's frequency = 1/pitch_in_px (px units)
        p = peaks_list[0]
        # Frequency in cy/px: r / max(h, w)? Actually FFT bin → freq:
        # freq_y = (py - cy) / h, freq_x = (px - cx) / w
        fy = p["dy"] / h
        fx = p["dx"] / w
        freq = float(np.hypot(fy, fx))
        if freq <= 0:
            return None
        return 1.0 / freq

    pitch1 = pitch_from(axis1_peaks, h, w)
    pitch2 = pitch_from(axis2_peaks, h, w)

    # Sub-harmonic detection on axis1:
    # For super-cell period N (in dies), expect a peak at radius r0/N along the same axis.
    sub_axis1 = {}
    for N in [2, 3, 4]:
        expected_r = r0 / N
        # Find any peak on axis1 with r close to expected_r
        candidates = [p for p in axis1_peaks if abs(p["r"] - expected_r) <= 3.0]
        if candidates:
            best = max(candidates, key=lambda p: p["amp"])
            sub_axis1[N] = {"r": best["r"], "expected_r": expected_r,
                            "amp": best["amp"], "ratio_vs_die": best["amp"] / p0["amp"]}
        else:
            sub_axis1[N] = {"r": None, "expected_r": expected_r,
                            "amp": 0.0, "ratio_vs_die": 0.0}

    sub_axis2 = {}
    if axis2_peaks:
        p0_ax2 = axis2_peaks[0]
        r0_ax2 = p0_ax2["r"]
        for N in [2, 3, 4]:
            expected_r = r0_ax2 / N
            candidates = [p for p in axis2_peaks if abs(p["r"] - expected_r) <= 3.0]
            if candidates:
                best = max(candidates, key=lambda p: p["amp"])
                sub_axis2[N] = {"r": best["r"], "expected_r": expected_r,
                                "amp": best["amp"], "ratio_vs_die": best["amp"] / p0_ax2["amp"]}
            else:
                sub_axis2[N] = {"r": None, "expected_r": expected_r,
                                "amp": 0.0, "ratio_vs_die": 0.0}

    return {
        "ang0_deg": ang0,
        "ang90_deg": ang90,
        "die_pitch_axis1_px": pitch1,
        "die_pitch_axis2_px": pitch2,
        "subharmonics_axis1": sub_axis1,
        "subharmonics_axis2": sub_axis2,
        "axis1_peaks": axis1_peaks[:8],
        "axis2_peaks": axis2_peaks[:8],
    }


def _save_diagnostic(gray: np.ndarray, mask: np.ndarray, diag: dict,
                     axes: dict, out: Path):
    fig, ax = plt.subplots(1, 2, figsize=(16, 8))
    ax[0].imshow(gray, cmap="gray")
    ax[0].imshow(np.where(mask, 0, 1), cmap="Reds", alpha=0.2)
    ax[0].set_title("Photo + mask (red ≈ excluded background/mount)")
    # FFT magnitude (log) zoomed near centre
    mag = diag["mag_sm"]
    h, w = mag.shape
    cy, cx = diag["centre"]
    half = 80
    sl_y = slice(cy - half, cy + half)
    sl_x = slice(cx - half, cx + half)
    log_mag = np.log10(mag[sl_y, sl_x] + 1)
    ax[1].imshow(log_mag, cmap="viridis")
    # Plot detected peaks
    for p in axes.get("axis1_peaks", []):
        ax[1].add_patch(plt.Circle((p["px"] - cx + half, p["py"] - cy + half),
                                    4, fill=False, color="red", lw=1.5))
    for p in axes.get("axis2_peaks", []):
        ax[1].add_patch(plt.Circle((p["px"] - cx + half, p["py"] - cy + half),
                                    4, fill=False, color="cyan", lw=1.5))
    ax[1].set_title("FFT log-magnitude (zoom); red = axis 1, cyan = axis 2")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)


def main() -> int:
    gray, mask = _load_gray_and_mask()
    diag = _fft_diagnostic(gray, mask)
    axes = _peaks_to_axes(diag)

    print(f"Image shape: {gray.shape}")
    print(f"Mask area (silicon pixels): {diag['mask_area_px']}")
    print()
    print("Primary axis angle (mod 180°):", axes.get("ang0_deg"))
    print("Orthogonal axis angle:", axes.get("ang90_deg"))
    print(f"Die pitch axis 1: {axes.get('die_pitch_axis1_px'):.2f} px"
          if axes.get("die_pitch_axis1_px") else "Die pitch axis 1: —")
    print(f"Die pitch axis 2: {axes.get('die_pitch_axis2_px'):.2f} px"
          if axes.get("die_pitch_axis2_px") else "Die pitch axis 2: —")
    print()
    print("Top axis-1 peaks (px coords centred on FFT-DC):")
    for p in axes.get("axis1_peaks", []):
        print(f"  dy={p['dy']:+4d} dx={p['dx']:+4d} r={p['r']:5.1f}"
              f" ang={p['ang_deg']:6.2f}° amp={p['amp']:.2e}")
    print()
    print("Top axis-2 peaks:")
    for p in axes.get("axis2_peaks", []):
        print(f"  dy={p['dy']:+4d} dx={p['dx']:+4d} r={p['r']:5.1f}"
              f" ang={p['ang_deg']:6.2f}° amp={p['amp']:.2e}")
    print()
    print("Sub-harmonic search on axis 1 (super-cell N = 2, 3, 4):")
    for N, info in axes.get("subharmonics_axis1", {}).items():
        print(f"  N={N}: expected r={info['expected_r']:.1f}"
              f"  found r={info['r']}  amp={info['amp']:.2e}"
              f"  ratio_vs_die={info['ratio_vs_die']:.3f}")
    print()
    print("Sub-harmonic search on axis 2:")
    for N, info in axes.get("subharmonics_axis2", {}).items():
        print(f"  N={N}: expected r={info['expected_r']:.1f}"
              f"  found r={info['r']}  amp={info['amp']:.2e}"
              f"  ratio_vs_die={info['ratio_vs_die']:.3f}")

    diag_png = OUT_DIR / "recon_grid_diagnostic.png"
    _save_diagnostic(gray, mask, diag, axes, diag_png)
    print(f"\nSaved diagnostic to {diag_png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
