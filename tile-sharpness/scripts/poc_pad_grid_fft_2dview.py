"""Quick 2D FFT image of the centre-tile crop to look for axis-aligned peaks."""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from tile_sharpness.phase1 import _decode_gray, _crop_box  # noqa: E402
from tile_sharpness.sweeps import discover_all, find_sweep  # noqa: E402

SWEEP_QUERY = "older-2026-01-29/2026-01-29__NIKKOR_Z_100-400mm_f_4.5-5.6_VR_S__1_2.60__F11"
OUT_DIR = Path(__file__).resolve().parent / "poc_pad_grid_fft_out"

sweep = find_sweep(SWEEP_QUERY, discover_all())
shot = sweep.shots[137]
cached = Path("/tmp/poc_jpegs") / shot.path.name
src_path = cached if cached.exists() else shot.path
full = _decode_gray(src_path)
# Centre tile
cx, cy = 4128, 2752
crop = _crop_box(full, (cx - 512, cy - 512, cx + 512, cy + 512))
print("crop shape:", crop.shape, "mean:", crop.mean())

# 2D FFT.
arr = crop.astype(np.float64) - crop.mean()
win = np.outer(np.hanning(arr.shape[0]), np.hanning(arr.shape[1]))
f = np.fft.fftshift(np.fft.fft2(arr * win))
amp = np.abs(f)
log_amp = np.log10(amp + 1)

fig, axes = plt.subplots(1, 2, figsize=(14, 7))
axes[0].imshow(crop, cmap="gray")
axes[0].set_title("centre tile, shot 137 (1024x1024)")
axes[0].axis("off")

# Show central portion of FFT (zoom in on low freq).
extent = [-0.5, 0.5, -0.5, 0.5]
axes[1].imshow(log_amp, cmap="viridis", extent=extent, origin="lower")
axes[1].set_title("log10 |FFT| (zoom on low-freq centre below)")
axes[1].set_xlabel("fx (cy/px)")
axes[1].set_ylabel("fy (cy/px)")

# Crop to +/-0.25 cy/px for clarity in inset.
h, w = log_amp.shape
cy0, cx0 = h // 2, w // 2
zoom_n = int(0.25 * h)  # +/- 0.25 cy/px
inset = log_amp[cy0 - zoom_n:cy0 + zoom_n, cx0 - zoom_n:cx0 + zoom_n]
fig2, ax = plt.subplots(figsize=(8, 8))
ax.imshow(inset, cmap="viridis", extent=[-0.25, 0.25, -0.25, 0.25], origin="lower")
ax.set_title("log10 |FFT|, +/- 0.25 cy/px zoom (centre tile, shot 137)")
ax.set_xlabel("fx (cy/px)")
ax.set_ylabel("fy (cy/px)")
fig.tight_layout()
fig.savefig(OUT_DIR / "fft2d_overview.png", dpi=120)
fig2.tight_layout()
fig2.savefig(OUT_DIR / "fft2d_zoom.png", dpi=120)

# Look for discrete peaks: subtract a smooth radial baseline.
fy = np.fft.fftshift(np.fft.fftfreq(h))
fx = np.fft.fftshift(np.fft.fftfreq(w))
fxx, fyy = np.meshgrid(fx, fy)
r = np.sqrt(fxx * fxx + fyy * fyy)

# For each pixel compute deviation from the radial median in a thin ring.
flat_r = r.ravel()
flat_a = amp.ravel()
order = np.argsort(flat_r)
sorted_r = flat_r[order]
sorted_a = flat_a[order]

# Running mean in win_len-wide windows via cumulative-sum, vectorised.
n = len(sorted_a)
win_len = max(200, n // 200)
half = win_len // 2
cs = np.concatenate([[0.0], np.cumsum(sorted_a)])
idx = np.arange(n)
lo = np.maximum(0, idx - half)
hi = np.minimum(n, idx + half)
baseline = (cs[hi] - cs[lo]) / (hi - lo)
# Map back: how many sigma above local mean is each pixel?
inv = np.empty(n, dtype=np.int64)
inv[order] = np.arange(n)
baseline_full = baseline[inv].reshape(amp.shape)
deviation = (amp - baseline_full) / (baseline_full + 1e-6)

# Mask out DC core.
mask_band = (r > 0.015) & (r < 0.25)
flat_dev = deviation.copy()
flat_dev[~mask_band] = -np.inf

# Find top 10 pixels in the deviation map.
flat = flat_dev.ravel()
top_idx = np.argpartition(flat, -10)[-10:]
top_idx = top_idx[np.argsort(flat[top_idx])[::-1]]
print("Top 10 anomalous pixels (deviation > local baseline):")
print("    fx        fy        r         pitch_um  dev_x_baseline")
for k in top_idx:
    fy_v = fyy.flat[k]
    fx_v = fxx.flat[k]
    r_v = r.flat[k]
    pitch_um = (0.3846 * 4.35 / r_v) if r_v > 0 else float("inf")
    print(f"  {fx_v:+.4f}  {fy_v:+.4f}  {r_v:.4f}  {pitch_um:8.2f}  {flat[k]:.2f}")

fig3, ax = plt.subplots(figsize=(8, 8))
zoom_dev = deviation[cy0 - zoom_n:cy0 + zoom_n, cx0 - zoom_n:cx0 + zoom_n]
ax.imshow(zoom_dev, cmap="hot", extent=[-0.25, 0.25, -0.25, 0.25], origin="lower",
          vmin=0, vmax=np.percentile(zoom_dev, 99.5))
ax.set_title("FFT deviation above local baseline (+/- 0.25 cy/px)")
ax.set_xlabel("fx (cy/px)"); ax.set_ylabel("fy (cy/px)")
fig3.tight_layout()
fig3.savefig(OUT_DIR / "fft2d_deviation_zoom.png", dpi=120)
print("saved fft2d_*.png to", OUT_DIR)
