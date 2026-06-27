"""Diagnose why sweep1 (M=0.385) scribe detection fails. Compare:
 - global tilt (current) vs tilt restricted to the wafer region,
 - long-line scribe signals at the wrong vs corrected tilt,
 - L threshold relative to FRAME height vs WAFER height.
True geometry (anchor_fit): theta=+4.77 deg, scale 0.632.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import cv2
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import rotate as ndi_rotate, sobel, binary_opening
from scipy.signal import find_peaks

HERE = Path(__file__).parent; A = HERE.parent; OUT = A / "out" / "diag_2026_06"
def _load(m, f):
    s = importlib.util.spec_from_file_location(m, HERE / f); x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x
mm = _load("mm", "register_method_morphological.py")
ra = _load("ra", "reg_auto.py")

path = ra.SWEEPS["sweep1_M0.385"][0]
gray, ds, (H, W) = mm.load_gray_downscaled(path)
print(f"gray_ds shape {gray.shape}, ds_scale {ds:.4f}")

# global tilt (current)
tilt_global = mm.detect_tilt_via_gradient(gray)
print(f"global tilt = {tilt_global:+.2f} deg  (true ~ +4.77)")

# tilt restricted to wafer region (erode so the fracture boundary doesn't vote)
wafer, _ = ra.wafer_mask(gray)
wafer_er = cv2.erode(wafer, np.ones((15, 15), np.uint8))
def tilt_masked(img, mask, rng=8.0, bw=0.25, pct=80.0):
    sx = sobel(img, axis=1); sy = sobel(img, axis=0); mag = np.hypot(sx, sy)
    m = (mask > 0)
    thr = np.percentile(mag[m], pct)
    strong = m & (mag > thr)
    ang = np.degrees(np.arctan2(sy[strong], sx[strong])); ang = (ang + 90) % 180 - 90
    bins = np.arange(-rng, rng + bw, bw); hist, _ = np.histogram(ang, bins=bins)
    centers = bins[:-1] + bw / 2; hist[np.abs(centers) < bw] = 0
    return float(bins[hist.argmax()] + bw / 2)
tilt_wafer = tilt_masked(gray, wafer_er)
print(f"wafer-masked tilt = {tilt_wafer:+.2f} deg   (wafer area {wafer.mean():.2f}, eroded {wafer_er.mean():.2f})")

def longline(img, mask, tilt, axis, frac_of, pct=80.0, prom=0.10):
    """axis=0 vertical scribes; frac_of='frame' or 'wafer'."""
    der = ndi_rotate(img, tilt, reshape=False, order=1, mode="reflect")
    mder = ndi_rotate(mask.astype(np.float32), tilt, reshape=False, order=1) > 0.5
    bp = mm.bandpass_image(der)
    work = bp if axis == 0 else bp.T
    mwork = mder if axis == 0 else mder.T
    edges = np.abs(sobel(work, axis=1)); thr = np.percentile(edges, pct)
    em = (edges > thr)
    if frac_of == "wafer":
        rows_with_wafer = np.where(mwork.any(axis=1))[0]
        span = (rows_with_wafer[-1] - rows_with_wafer[0]) if rows_with_wafer.size else work.shape[0]
        L = max(5, int(span * 0.40))
    else:
        L = max(5, int(work.shape[0] * 0.40))
    opened = binary_opening(em, structure=np.ones((L, 1), bool))
    sig = opened.sum(axis=0).astype(np.float32)
    pk = find_peaks(sig / max(sig.max(), 1), distance=8, prominence=prom)[0] if sig.max() > 0 else np.array([])
    return sig, pk, L

fig, ax = plt.subplots(3, 2, figsize=(16, 14))
for r, (tilt, name) in enumerate([(tilt_global, f"global {tilt_global:+.1f}"),
                                   (tilt_wafer, f"wafer {tilt_wafer:+.1f}"),
                                   (4.77, "true +4.77")]):
    der = ndi_rotate(gray, tilt, reshape=False, order=1, mode="reflect")
    ax[r, 0].imshow(der, cmap="gray"); ax[r, 0].set_title(f"de-rotated @ {name}")
    for axis, col, frac in [(0, "cyan", "frame"), (1, "orange", "frame"), (0, "lime", "wafer"), (1, "red", "wafer")]:
        sig, pk, L = longline(gray, wafer, tilt, axis, frac)
        lbl = ("col" if axis == 0 else "row") + f"/{frac}: {len(pk)}pk L={L}"
        ax[r, 1].plot(sig / max(sig.max(), 1) + (0.0 if frac == "frame" else 1.2),
                      color=col, lw=0.8, label=lbl)
    ax[r, 1].set_title(f"long-line signals @ {name}"); ax[r, 1].legend(fontsize=7)
fig.tight_layout(); fig.savefig(OUT / "sweep1_scribes.png", dpi=90)
print(f"saved {OUT/'sweep1_scribes.png'}")

# report peak counts for the promising config
for tilt, nm in [(tilt_global, "global"), (tilt_wafer, "wafer"), (4.77, "true")]:
    for frac in ("frame", "wafer"):
        _, cpk, _ = longline(gray, wafer, tilt, 0, frac)
        _, rpk, _ = longline(gray, wafer, tilt, 1, frac)
        print(f"  tilt={nm:6s} frac={frac:5s}: {len(cpk)} cols, {len(rpk)} rows")
