"""Task 17 (handover follow-up #4): atlas-anchored bond-pad sharpness on the
POC-C sweep, to fix POC C's two failures (57% coverage, shot-to-shot
non-determinism).

POC C searched each tile for an "isolated wider feature" to use as an MTF50
target. That is content-dependent (43% of tiles had none) and unstable
(percentile-threshold drift moved the detected feature shot-to-shot).

Here instead we use the atlas: it knows WHERE every bond-pad grid is (bbox_uv
per die type) and its PITCH. We register the sweep once (anchor affine), project
every in-FOV bond-pad component to fixed sub-pixel image locations, and read the
pad-grid FFT amplitude at the atlas-known pitch on every shot. Locations are
fixed => deterministic; every die's pads are known => full coverage.

Reports, vs POC C:
  - coverage: in-FOV bond-pad components that yield a valid reading (target ~100%)
  - determinism: per-component focus-curve smoothness + argmax stability across
    shots (POC C flipped wildly between adjacent shots).

REGISTRATION (2026-06-27 follow-up): by default the sweep is registered
AUTONOMOUSLY via ``reg_auto.register_and_refine`` (no hand-clicked anchors); the
refined affine's radial term (non-macro lens) is honored via
``reg_auto.grid_xy_distorted``. Pass ``--manual`` for the hand-clicked anchors.

Output: out/diag_2026_06/task17_bondpad_atlas.{json,png}
Sweep: sweep1 (NIKKOR Z 100-400 @ 0.385x F11) == POC C's sweep.
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

HERE = Path(__file__).parent
A = HERE.parent
OUT = A / "out" / "diag_2026_06"
OUT.mkdir(parents=True, exist_ok=True)

def _load_sibling(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


af = _load_sibling("anchor_fit_sweep")
# Autonomous registration (default); grid_xy_distorted honors the radial term.
reg_auto = _load_sibling("reg_auto")

ATLAS = json.load(open(A / "atlas.json"))
ANCHORS = json.load(open(A / "out" / "sweep_anchors" / "anchor_fit_params.json"))

SWEEP = "sweep1_M0.385"
SWEEP_DIR = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
                 "NIKKOR Z 100-400mm f_4.5-5.6 VR S/1_2.60/F11")
IMAGE_W, IMAGE_H = 8256, 5504


def die_uv_to_img(col, row, u, v, p):
    """col,row are die indices (0-based). u,v in [0,1] within the die."""
    if "k1" in p:        # non-macro lens: honor the radial-distortion term
        return reg_auto.grid_xy_distorted(col + u, row + v, p)
    return af.grid_xy(col + u, row + v, p, ATLAS)


def enumerate_regions(p):
    """All (die_col, die_row, comp_idx, bbox_img, pitch_uv_img) in-FOV."""
    scale = p["scale"]
    regions = []
    for col in range(0, 11):          # die columns 0..10
        for row in range(0, 6):       # die rows A..F = 0..5
            typ = f"({col % 4}, {row % 4})"
            dt = ATLAS["die_types"].get(typ, {})
            for ci, bp in enumerate(dt.get("feature_inventory", {}).get("bond_pads", [])):
                u0, v0, u1, v1 = bp["bbox_uv"]
                corners = [die_uv_to_img(col, row, u, v, p)
                           for (u, v) in [(u0, v0), (u0, v1), (u1, v0), (u1, v1)]]
                xs = [c[0] for c in corners]; ys = [c[1] for c in corners]
                cx, cy = np.mean(xs), np.mean(ys)
                margin = 60
                if not (margin < cx < IMAGE_W - margin and margin < cy < IMAGE_H - margin):
                    continue
                # require the whole bbox reasonably in-frame
                if min(xs) < 0 or max(xs) >= IMAGE_W or min(ys) < 0 or max(ys) >= IMAGE_H:
                    continue
                pp = bp.get("pad_pitch_px") or {}
                pu = pp.get("pitch_u_px"); pv = pp.get("pitch_v_px")
                regions.append(dict(
                    col=col, row=row, type=typ, comp=ci,
                    label=f"{col}{'ABCDEF'[row]}#{ci}",
                    bbox=(min(xs), min(ys), max(xs), max(ys)),
                    # pad pitch in SWEEP px = pitch_in_0129 * sweep_scale
                    pu_sweep=(pu * scale) if pu else None,
                    pv_sweep=(pv * scale) if pv else None))
    return regions


def pad_fft_amp(roi, pitch_px, theta_deg, axis):
    """De-rotate ROI, take the 1-D profile along `axis` (0=x/u, 1=y/v) averaged
    over the other axis, FFT, return |amplitude| at the pad fundamental."""
    if pitch_px is None or pitch_px < 2.5 or roi.size == 0 or min(roi.shape) < 8:
        return None
    h, w = roi.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), theta_deg, 1.0)
    der = cv2.warpAffine(roi.astype(np.float32), M, (w, h),
                         flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    # trim rotation seam
    t = max(2, int(0.08 * min(h, w)))
    der = der[t:h - t, t:w - t]
    if min(der.shape) < 8:
        return None
    prof = der.mean(axis=1) if axis == 1 else der.mean(axis=0)
    prof = prof - prof.mean()
    n = prof.size
    if n < 8:
        return None
    mag = np.abs(np.fft.rfft(prof * np.hanning(n)))
    freqs = np.fft.rfftfreq(n, d=1.0)
    f0 = 1.0 / pitch_px
    if f0 >= freqs[-1]:
        return None
    idx = int(np.argmin(np.abs(freqs - f0)))
    # take the max in a small neighbourhood to tolerate pitch error
    lo, hi = max(1, idx - 2), min(len(mag), idx + 3)
    return float(mag[lo:hi].max())


def main():
    use_manual = "--manual" in sys.argv
    if use_manual:
        p = ANCHORS[SWEEP]
        print("registration source: manual anchors")
    else:
        p = reg_auto.register_and_refine(SWEEP)
        if p is None:
            print(f"reg_auto FAILED for {SWEEP}; cannot proceed")
            return
        print(f"registration source: autonomous reg_auto "
              f"({p.get('reg_method')}, col={p.get('reg_col_first')} row={p.get('reg_row_first')}, "
              f"fit_rmse={p.get('reg_fit_rmse_px'):.2f}px, "
              f"{'+radial' if 'k1' in p else 'similarity'})")
    theta_deg = p["theta_deg"]
    regions = enumerate_regions(p)
    shots = sorted(SWEEP_DIR.glob("*.jpg")) + sorted(SWEEP_DIR.glob("*.JPG"))
    print(f"{SWEEP}: {len(shots)} shots, {len(regions)} in-FOV bond-pad components")

    # curves[region_idx][axis] = list over shots; also lapvar (gradient energy)
    curves = {i: {"u": [], "v": [], "lap": []} for i in range(len(regions))}
    for sp in shots:
        img = np.asarray(Image.open(sp).convert("L"))
        for i, r in enumerate(regions):
            x0, y0, x1, y1 = [int(v) for v in r["bbox"]]
            roi = img[y0:y1, x0:x1]
            curves[i]["u"].append(pad_fft_amp(roi, r["pu_sweep"], theta_deg, axis=0))
            curves[i]["v"].append(pad_fft_amp(roi, r["pv_sweep"], theta_deg, axis=1))
            curves[i]["lap"].append(float(cv2.Laplacian(roi.astype(np.float32),
                                                         cv2.CV_32F).var())
                                    if roi.size and min(roi.shape) >= 8 else np.nan)

    # combine u & v into one focus signal per region (max of the two, per shot)
    def smooth(x, k=7):
        if x.size < k:
            return x
        ker = np.ones(k) / k
        return np.convolve(np.nan_to_num(x, nan=np.nanmedian(x)), ker, mode="same")

    SNR_MIN = 1.8
    results = []
    n_valid_regions = 0
    usable = {"padfft": [], "lapvar": []}   # argmaxes of usable components per metric

    def metric_stats(arr):
        valid = np.isfinite(arr).sum()
        if valid < len(shots) * 0.8:
            return None
        cs = smooth(arr)
        am = int(np.nanargmax(cs))
        med = np.nanmedian(arr)
        snr = float(np.nanmax(cs) / med) if med > 0 else 0.0
        return dict(argmax=am, snr=snr, usable=snr >= SNR_MIN, comb=cs.tolist())

    for i, r in enumerate(regions):
        u = np.array([x if x is not None else np.nan for x in curves[i]["u"]], float)
        v = np.array([x if x is not None else np.nan for x in curves[i]["v"]], float)
        padfft = np.nanmax(np.vstack([u, v]), axis=0)
        lap = np.array(curves[i]["lap"], float)
        sp_pad = metric_stats(padfft)
        sp_lap = metric_stats(lap)
        rec = dict(label=r["label"], type=r["type"], col=r["col"], row=r["row"],
                   padfft=sp_pad, lapvar=sp_lap)
        if sp_pad or sp_lap:
            n_valid_regions += 1
        for key, sp in (("padfft", sp_pad), ("lapvar", sp_lap)):
            if sp and sp["usable"]:
                usable[key].append(sp["argmax"])
        results.append(rec)

    coverage = n_valid_regions / len(regions) if regions else 0.0
    print(f"\nCOVERAGE (any valid reading >=80% of shots): {n_valid_regions}/{len(regions)} "
          f"= {coverage*100:.0f}%   (POC C: 57%)")
    for key in ("padfft", "lapvar"):
        n_u = len(usable[key])
        line = f"USABLE FOCUS [{key}] (peak/median SNR >= {SNR_MIN}): {n_u}/{len(regions)} = {n_u/len(regions)*100:.0f}%"
        if usable[key]:
            am = np.array(usable[key])
            line += (f"  argmax median {int(np.median(am))} IQR "
                     f"[{int(np.percentile(am,25))},{int(np.percentile(am,75))}]")
        print(line)
    print("DETERMINISM: method has NO stochastic step (fixed atlas locations, no "
          "re-detection) => identical output run-to-run, unlike POC C's LSD-ordering flips.")

    json.dump(dict(sweep=SWEEP, n_shots=len(shots), n_regions=len(regions),
                   coverage=coverage, n_valid=n_valid_regions,
                   registration=dict(method=p.get("reg_method", "manual"),
                                     fit_rmse_px=p.get("reg_fit_rmse_px"),
                                     col_first=p.get("reg_col_first"),
                                     row_first=p.get("reg_row_first"),
                                     has_distortion=("k1" in p)),
                   results=results),
              open(OUT / "task17_bondpad_atlas.json", "w"), indent=1, default=float)

    # plot usable lapvar focus curves + argmax histogram (lapvar is the stronger metric)
    fig, ax = plt.subplots(1, 2, figsize=(16, 6))
    plotted = 0
    for r in results:
        sp = r["lapvar"]
        if not (sp and sp["usable"]):
            continue
        c = np.array(sp["comb"], float)
        ax[0].plot(c / np.nanmax(c), lw=0.8, alpha=0.5)
        plotted += 1
    ax[0].axvline(138, color="g", ls="--", label="sweep1 true LSF-centre focus (138)")
    ax[0].set_title(f"{SWEEP} usable bond-pad focus curves [lapvar] ({plotted} components)")
    ax[0].set_xlabel("shot"); ax[0].set_ylabel("lapvar / max"); ax[0].grid(alpha=.3); ax[0].legend()
    if usable["lapvar"]:
        ax[1].hist(usable["lapvar"], bins=24, color="C0", alpha=0.8)
        ax[1].axvline(138, color="g", ls="--", label="LSF-centre 138")
    ax[1].set_title("usable-component [lapvar] focus argmax distribution")
    ax[1].set_xlabel("focus shot"); ax[1].set_ylabel("# components"); ax[1].grid(alpha=.3); ax[1].legend()
    fig.tight_layout()
    fig.savefig(OUT / "task17_bondpad_atlas.png", dpi=110)
    print(f"\nsaved {OUT/'task17_bondpad_atlas.png'} and .json")


if __name__ == "__main__":
    main()
