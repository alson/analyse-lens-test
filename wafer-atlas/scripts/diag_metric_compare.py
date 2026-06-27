"""Task #1: compare candidate focus-discrimination metrics on the 4D bar, to
replace the saturating MTF50 argmax. For a sweep + instance, per shot (with
per-shot bar tracking) compute:

  mtf50        - current metric (saturates / flat-tops)
  peak_amp10   - |FFT(LSF)| at 0.10 cy/px (current secondary)
  peak_amp25   - |FFT(LSF)| at 0.25 cy/px (higher freq, more discriminating)
  acutance     - max |gradient| of the bar edge ESF (LSF peak height)
  tenengrad    - Sobel gradient energy over the bar ROI (classic focus measure)
  lapvar       - variance of Laplacian over the bar ROI (classic focus measure)

Plots all normalized on one axis vs the LSF reference shot.
Usage: diag_metric_compare.py <sweep_name> <col>
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

from tile_sharpness.methods.lsf import cross_section, lsf_mtf50, lsf_peak_amp, _split_to_edge_lsfs

_spec = importlib.util.spec_from_file_location(
    "diag_measure", Path(__file__).parent / "diag_measure.py")
dm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dm)

A = Path(__file__).parent.parent
OUT = A / "out" / "diag_2026_06"


def peak_amp_at(profile, f):
    pair = _split_to_edge_lsfs(profile)
    if pair is None:
        return 0.0
    from tile_sharpness.methods.lsf import _lsf_fft
    amps = []
    for lsf in pair:
        freqs, mag = _lsf_fft(lsf)
        if freqs.size:
            amps.append(float(mag[int(np.argmin(np.abs(freqs - f)))]))
    return float(np.mean(amps)) if amps else 0.0


def acutance(profile):
    """Max gradient magnitude of the bar edge (peak of the LSF)."""
    pair = _split_to_edge_lsfs(profile)
    if pair is None:
        return 0.0
    return float(np.mean([np.abs(lsf).max() for lsf in pair]))


def main():
    name, col = sys.argv[1], int(sys.argv[2])
    cfg = {c["name"]: c for c in dm.task15.SWEEPS}[name]
    aff = dm.anchors[name]
    shots = sorted(cfg["dir"].glob("*.jpg")) + sorted(cfg["dir"].glob("*.JPG"))
    geo = dm.instance_geometry(aff, col)
    rx0, ry0, rx1, ry1 = geo["roi"]
    bar_w, bar_h = geo["w_px"], abs(geo["y_top"] - geo["y_bottom"])
    pred_cx, pred_cy = geo["cx"] - rx0, geo["cy"] - ry0

    M = {k: [] for k in ("mtf50", "amp10", "amp25", "acut", "teneng", "lapvar")}
    for sp in shots:
        img = np.asarray(Image.open(sp).convert("L"))
        roi = img[ry0:min(img.shape[0], ry1), rx0:min(img.shape[1], rx1)]
        d = dm.detect_bar_segment(roi, pred_cx, pred_cy, bar_w, bar_h)
        if d is None:
            for k in M:
                M[k].append(np.nan)
            continue
        seg, hw, (dcx, dcy), short = d
        prof = cross_section(roi.astype(np.float32), seg, half_window_px=hw)
        M["mtf50"].append(lsf_mtf50(prof) or np.nan)
        M["amp10"].append(peak_amp_at(prof, 0.10))
        M["amp25"].append(peak_amp_at(prof, 0.25))
        M["acut"].append(acutance(prof))
        # gradient-energy metrics on a tight box around the detected bar
        half = int(max(bar_w, bar_h) * 0.7)
        y0 = max(0, int(dcy - half)); y1 = min(roi.shape[0], int(dcy + half))
        x0 = max(0, int(dcx - half)); x1 = min(roi.shape[1], int(dcx + half))
        box = roi[y0:y1, x0:x1].astype(np.float32)
        gx = cv2.Sobel(box, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(box, cv2.CV_32F, 0, 1, ksize=3)
        M["teneng"].append(float((gx * gx + gy * gy).mean()))
        M["lapvar"].append(float(cv2.Laplacian(box, cv2.CV_32F).var()))

    ref = cfg["lsf_ref_shot"]
    print(f"{name} col {col}D  ref={ref}")
    for k, v in M.items():
        arr = np.array(v, float)
        if np.all(np.isnan(arr)):
            print(f"  {k:8s}: all-nan"); continue
        am = int(np.nanargmax(arr))
        gap = (am - ref) if ref is not None else None
        print(f"  {k:8s}: argmax shot {am}" + (f"  gap {gap:+d}" if gap is not None else "  gap n/a"))

    fig, ax = plt.subplots(figsize=(13, 5))
    for k, v in M.items():
        arr = np.array(v, float)
        if np.all(np.isnan(arr)):
            continue
        n = arr / np.nanmax(arr)
        ax.plot(n, lw=1.3, label=f"{k} (argmax {int(np.nanargmax(arr))})")
    if ref is not None:
        ax.axvline(ref, color="k", ls="--", alpha=0.6, label=f"LSF ref {ref}")
    ax.set_title(f"{name} col {col}D — normalized focus metrics")
    ax.set_xlabel("shot"); ax.set_ylabel("metric / max"); ax.grid(alpha=0.3)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    p = OUT / f"{name}_col{col}_metrics.png"
    fig.savefig(p, dpi=120); plt.close(fig)
    print(f"saved {p}")


if __name__ == "__main__":
    main()
