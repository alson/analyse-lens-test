"""Diagnostic: plot radial spectra of the sharpest center tiles for each
100-400 config to see where the lens differences actually live.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

DATA_ROOT = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-28")
OUT = Path(__file__).parent / "poc_longdist_100_400_tc_2026_01_28_out"
OUT.mkdir(exist_ok=True)

TILE = 256


def load_luma(p: Path) -> np.ndarray:
    return np.asarray(Image.open(p).convert("L"), dtype=np.float32)


def radial_spectrum(tile: np.ndarray) -> np.ndarray:
    tile = tile - tile.mean()
    n = tile.shape[0]
    w = np.hanning(n)
    tile = tile * np.outer(w, w)
    F = np.fft.fftshift(np.fft.fft2(tile))
    P = (F.real ** 2 + F.imag ** 2)
    cy, cx = n // 2, n // 2
    y, x = np.indices(P.shape)
    r = np.sqrt((y - cy) ** 2 + (x - cx) ** 2).astype(np.int32)
    rmax = n // 2
    radial = np.bincount(r.ravel(), P.ravel(), minlength=rmax + 1)[: rmax + 1]
    counts = np.bincount(r.ravel(), minlength=rmax + 1)[: rmax + 1]
    counts = np.maximum(counts, 1)
    return radial / counts


def best_center_tile(luma: np.ndarray) -> np.ndarray:
    """Find the highest-gradient tile near frame center: that's the
    sharpest in-focus patch."""
    h, w = luma.shape
    # Search a 1500x1500 box at center
    cy, cx = h // 2, w // 2
    box = luma[cy - 750 : cy + 750, cx - 750 : cx + 750]
    best = None
    best_score = -1
    for y in range(0, box.shape[0] - TILE + 1, 64):
        for x in range(0, box.shape[1] - TILE + 1, 64):
            t = box[y : y + TILE, x : x + TILE]
            # Use gradient magnitude variance as quick sharpness proxy
            gy = np.diff(t, axis=0)
            gx = np.diff(t, axis=1)
            score = (gy * gy).mean() + (gx * gx).mean()
            if score > best_score:
                best_score = score
                best = t
    return best


# (label, path-rel)
CONFIGS = [
    ("bare 400 F8",  "NIKKOR Z 100-400mm f_4.5-5.6 VR S/400.0 mm/F8"),
    ("bare 400 F11", "NIKKOR Z 100-400mm f_4.5-5.6 VR S/400.0 mm/F11"),
    ("+TC14 400 F8", "NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x/400.0 mm/F8"),
    ("+TC14 400 F11","NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-1.4x/400.0 mm/F11"),
    ("+TC20 400 F11","NIKKOR Z 100-400mm f_4.5-5.6 VR S Z TC-2.0x/400.0 mm/F11"),
]


def best_replicate(d: Path) -> Path:
    """Return the replicate with the sharpest center tile."""
    best_p, best_t, best_score = None, None, -1
    for jp in sorted(d.glob("*.jpg")):
        luma = load_luma(jp)
        t = best_center_tile(luma)
        gy = np.diff(t, axis=0); gx = np.diff(t, axis=1)
        s = (gy * gy).mean() + (gx * gx).mean()
        if s > best_score:
            best_score, best_p, best_t = s, jp, t
    return best_p, best_t


fig, axes = plt.subplots(1, 2, figsize=(14, 6))
ax_lin, ax_log = axes

freqs = np.arange(TILE // 2 + 1) / TILE  # 0..0.5 cy/px

for label, rel in CONFIGS:
    d = DATA_ROOT / rel
    p, tile = best_replicate(d)
    spec = radial_spectrum(tile)
    ax_lin.plot(freqs, spec / spec[1], label=label)
    ax_log.loglog(freqs[1:], spec[1:] / spec[1], label=label)

ax_lin.set_xlabel("frequency (cy/pixel)")
ax_lin.set_ylabel("radial power (norm to f=1/N)")
ax_lin.set_title("Radial power spectrum, best-center tile per config (linear)")
ax_lin.legend()
ax_lin.grid(True, alpha=0.3)

ax_log.set_xlabel("frequency (cy/pixel)")
ax_log.set_ylabel("radial power (norm)")
ax_log.set_title("Same (log-log)")
ax_log.legend()
ax_log.grid(True, alpha=0.3, which="both")

fig.tight_layout()
out_path = OUT / "diag_radial_spectra.png"
fig.savefig(out_path, dpi=120)
print(f"wrote {out_path}")

# Also dump high-frequency power ratios as a numeric sanity check
print("\nHigh-frequency power fraction (f > 0.15 cy/px):")
for label, rel in CONFIGS:
    d = DATA_ROOT / rel
    _, tile = best_replicate(d)
    spec = radial_spectrum(tile)
    total = spec[1:].sum()
    hf = spec[int(0.15 * TILE):].sum()
    print(f"  {label:18s}  hf/total = {hf/total:.4f}   peak={spec[1]:.0f}  hf_sum={hf:.0f}")
