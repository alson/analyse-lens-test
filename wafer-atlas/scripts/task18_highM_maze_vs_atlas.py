"""Task 18 (HANDOVER item #4 / Pending §3): atlas at high M vs the maze-FFT.

The established high-M focus metric is the fine-maze 2D-FFT (`tile_sharpness.
methods.maze_fft.maze_amp`): one FFT annulus at the wafer's ~13 µm maze
fundamental, computed on a tile-CENTRED ROI with a generic pitch. It is the
primary metric for M >= 0.7 (LSF is the fallback). Pending §3 asked whether the
atlas — which knows per-die bond-pad PITCHES and exact feature LOCATIONS — could
replace or augment it.

This compares, on the high-M sweeps (sweep2 M=1.0 AF200, sweep3 M=2.0 TC-2001),
three ATLAS-ANCHORED, deterministically-placed per-shot focus signals over every
in-FOV die, against the tile-sharpness CSV references:

  1. maze_amp  — the SAME maze-FFT metric, but on an atlas-anchored die-centred
     ROI (deterministic placement / full coverage) instead of the pipeline's
     blind tile centre. Tests whether atlas placement helps the maze signal.
  2. pad-FFT   — FFT amplitude at the atlas-known per-die bond-pad pitch
     (task17's de-rotated 1-D profile method). Tests the §3 "per-die pad pitch"
     idea directly.
  3. lapvar    — Laplacian variance on the same ROI (the gradient-energy
     gold-standard that won at low M in task17 / REPORT item #1).

References (centre tile, from the per-shot CSVs): true lsf_mtf50 argmax and the
pipeline maze_fft_amp argmax. Registration is AUTONOMOUS (reg_auto).

Output: out/diag_2026_06/task18_highM_maze_vs_atlas.{json,png} + printed summary.
Run on nufan (full-frame decode x n_shots x 2 sweeps).
"""
from __future__ import annotations

import csv
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from tile_sharpness.methods.maze_fft import maze_amp

HERE = Path(__file__).parent
A = HERE.parent
OUT = A / "out" / "diag_2026_06"
TS = Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness")
IMAGE_W, IMAGE_H = 8256, 5504


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


reg_auto = _load("reg_auto")
af = _load("anchor_fit_sweep")
ATLAS = json.load(open(A / "atlas.json"))

SWEEPS = [
    dict(name="sweep2_M1.0", M=1.0,
         dir=Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
                  "Nikon AF Micro-Nikkor 200mm f_4D IF-ED/1_1/F11"),
         ref_csv=(TS / "out_apertures_for_calibration/per_shot_per_tile.csv",
                  "200mm_f_4D_IF-ED__1_1__F11")),
    dict(name="sweep3_M2.0", M=2.0,
         dir=Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
                  "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001/2_1/F11"),
         ref_csv=(TS / "out_task4/per_shot_per_tile.csv", "TC-2001")),
]


def die_uv_to_img(col, row, u, v, p):
    if "k1" in p:
        return reg_auto.grid_xy_distorted(col + u, row + v, p)
    return af.grid_xy(col + u, row + v, p, ATLAS)


def csv_reference(ref_csv):
    """Centre-tile lsf_mtf50 + maze_fft_amp focus argmaxes from the CSV."""
    path, key = ref_csv
    if not path.exists():
        return {}
    by_tile = defaultdict(list)
    with open(path) as f:
        for r in csv.DictReader(f):
            if key in r["sweep"]:
                by_tile[(r["tile_ix"], r["tile_iy"])].append(r)
    centre = by_tile.get(("0", "0")) or next(iter(by_tile.values()), [])

    def am(col):
        best = None
        for r in centre:
            try:
                v = float(r[col])
            except (ValueError, KeyError):
                continue
            if v <= 0:
                continue
            si = int(r["shot_idx"])
            if best is None or v > best[1]:
                best = (si, v)
        return best and best[0]
    return {"lsf": am("lsf_mtf50_cy_per_px"), "maze": am("maze_fft_amp")}


def enumerate_dies(p):
    """In-FOV die centres (col,row) with the largest per-die bond-pad pitch (for
    the pad-FFT target). Margin keeps the whole die-centred ROI on-image."""
    scale = p["scale"]
    dies = []
    for col in range(0, 11):
        for row in range(0, 6):
            cx, cy = die_uv_to_img(col, row, 0.5, 0.5, p)
            # die extent in px (approx, via the four die corners)
            corners = [die_uv_to_img(col, row, u, v, p) for u, v in
                       ((0, 0), (0, 1), (1, 0), (1, 1))]
            xs = [c[0] for c in corners]; ys = [c[1] for c in corners]
            half = 0.30 * min(max(xs) - min(xs), max(ys) - min(ys))
            if half < 96:
                continue
            if not (half < cx < IMAGE_W - half and half < cy < IMAGE_H - half):
                continue
            # largest pad pitch in this die type -> pad-FFT fundamental
            typ = f"({col % 4}, {row % 4})"
            pads = ATLAS["die_types"].get(typ, {}).get("feature_inventory", {}).get("bond_pads", [])
            best_pitch = 0.0
            for bp in pads:
                pp = bp.get("pad_pitch_px") or {}
                for kk in ("pitch_u_px", "pitch_v_px"):
                    if pp.get(kk):
                        best_pitch = max(best_pitch, pp[kk])
            dies.append(dict(col=col, row=row, cx=cx, cy=cy, half=int(half),
                             pad_pitch_sweep=(best_pitch * scale if best_pitch else None)))
    return dies


def pad_fft_amp(roi, pitch_px, theta_deg):
    """De-rotate, 1-D profile (avg over short axis), FFT amplitude at the pad
    fundamental (max in a small neighbourhood). Mirrors task17."""
    if pitch_px is None or pitch_px < 2.5 or roi.size == 0 or min(roi.shape) < 8:
        return None
    best = 0.0
    h, w = roi.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), theta_deg, 1.0)
    der = cv2.warpAffine(roi.astype(np.float32), M, (w, h),
                         flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    t = max(2, int(0.08 * min(h, w)))
    der = der[t:h - t, t:w - t]
    if min(der.shape) < 8:
        return None
    for axis in (0, 1):
        prof = der.mean(axis=1) if axis == 1 else der.mean(axis=0)
        prof = prof - prof.mean()
        n = prof.size
        if n < 8:
            continue
        mag = np.abs(np.fft.rfft(prof * np.hanning(n)))
        freqs = np.fft.rfftfreq(n, d=1.0)
        f0 = 1.0 / pitch_px
        if f0 >= freqs[-1]:
            continue
        idx = int(np.argmin(np.abs(freqs - f0)))
        lo, hi = max(1, idx - 2), min(len(mag), idx + 3)
        best = max(best, float(mag[lo:hi].max()))
    return best if best > 0 else None


def smooth(x, k=7):
    if x.size < k:
        return x
    return np.convolve(np.nan_to_num(x, nan=np.nanmedian(x)), np.ones(k) / k, mode="same")


def metric_stats(arr, n_shots, snr_min=1.8):
    valid = np.isfinite(arr).sum()
    if valid < n_shots * 0.8:
        return None
    cs = smooth(arr)
    med = np.nanmedian(arr)
    snr = float(np.nanmax(cs) / med) if med > 0 else 0.0
    return dict(argmax=int(np.nanargmax(cs)), snr=snr, usable=snr >= snr_min)


def run_sweep(cfg):
    name, M = cfg["name"], cfg["M"]
    p = reg_auto.register_and_refine(name)
    if p is None:
        print(f"{name}: reg_auto FAILED"); return None
    theta_deg = p["theta_deg"]
    dies = enumerate_dies(p)
    shots = sorted(cfg["dir"].glob("*.jpg")) + sorted(cfg["dir"].glob("*.JPG"))
    ref = csv_reference(cfg["ref_csv"])
    print(f"\n{'='*70}\n=== {name} (M={M}) ===  {len(shots)} shots, {len(dies)} in-FOV dies"
          f"  reg={p['reg_method']} fit={p['reg_fit_rmse_px']:.2f}px\n{'='*70}")
    print(f"  CSV refs: lsf={ref.get('lsf')}  maze={ref.get('maze')}")

    curves = {i: {"maze": [], "pad": [], "lap": []} for i in range(len(dies))}
    for sp in shots:
        img = np.asarray(Image.open(sp).convert("L"))
        for i, d in enumerate(dies):
            hw = d["half"]
            y0, y1 = max(0, d["cy"] - hw), min(img.shape[0], d["cy"] + hw)
            x0, x1 = max(0, d["cx"] - hw), min(img.shape[1], d["cx"] + hw)
            roi = img[int(y0):int(y1), int(x0):int(x1)]
            if roi.size == 0 or min(roi.shape) < 16:
                curves[i]["maze"].append(np.nan); curves[i]["pad"].append(np.nan)
                curves[i]["lap"].append(np.nan); continue
            mz = maze_amp(roi, M)
            curves[i]["maze"].append(mz if mz is not None else np.nan)
            pf = pad_fft_amp(roi, d["pad_pitch_sweep"], theta_deg)
            curves[i]["pad"].append(pf if pf is not None else np.nan)
            curves[i]["lap"].append(float(cv2.Laplacian(roi.astype(np.float32), cv2.CV_32F).var()))

    summary = {k: {"argmaxes": [], "usable": 0} for k in ("maze", "pad", "lap")}
    per_die = []
    for i, d in enumerate(dies):
        rec = dict(col=d["col"], row=d["row"])
        for k in ("maze", "pad", "lap"):
            st = metric_stats(np.array(curves[i][k], float), len(shots))
            rec[k] = st
            if st:
                summary[k]["argmaxes"].append(st["argmax"])
                summary[k]["usable"] += int(st["usable"])
        per_die.append(rec)

    print(f"  {'metric':<8}{'usable':<9}{'argmax median':<15}{'IQR':<12}{'gap vs LSF'}")
    out = {}
    for k, lbl in (("maze", "maze-FFT (atlas ROI)"), ("pad", "pad-FFT (atlas pitch)"),
                   ("lap", "lapvar (atlas ROI)")):
        ams = np.array(summary[k]["argmaxes"])
        if ams.size:
            med = int(np.median(ams)); iqr = (int(np.percentile(ams, 25)), int(np.percentile(ams, 75)))
            gap = (med - ref["lsf"]) if ref.get("lsf") is not None else None
            print(f"  {lbl:<22}{summary[k]['usable']}/{len(dies):<6}{med:<15}"
                  f"{str(iqr):<12}{(f'{gap:+d}' if gap is not None else '-')}")
            out[k] = dict(usable=summary[k]["usable"], n_dies=len(dies),
                          median=med, iqr=list(iqr), gap_vs_lsf=gap)
        else:
            print(f"  {lbl:<22}0/{len(dies)} usable")
            out[k] = dict(usable=0, n_dies=len(dies))
    return dict(name=name, M=M, n_shots=len(shots), n_dies=len(dies), ref=ref,
                registration=dict(method=p["reg_method"], fit_rmse_px=p["reg_fit_rmse_px"]),
                metrics=out, per_die=per_die, curves={str(i): curves[i] for i in range(len(dies))})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = [r for r in (run_sweep(cfg) for cfg in SWEEPS) if r]

    fig, axes = plt.subplots(len(results), 3, figsize=(18, 4.5 * len(results)), squeeze=False)
    for row, r in enumerate(results):
        for col, (k, lbl) in enumerate((("maze", "maze-FFT (atlas ROI)"),
                                        ("pad", "pad-FFT (atlas pitch)"),
                                        ("lap", "lapvar (atlas ROI)"))):
            ax = axes[row][col]
            for i in r["curves"]:
                arr = np.array(r["curves"][i][k], float)
                if np.isfinite(arr).sum() < r["n_shots"] * 0.8:
                    continue
                cs = smooth(arr)
                mx = np.nanmax(cs)
                if mx > 0:
                    ax.plot(cs / mx, lw=0.7, alpha=0.5)
            if r["ref"].get("lsf") is not None:
                ax.axvline(r["ref"]["lsf"], color="g", ls="--", label=f"LSF {r['ref']['lsf']}")
            if r["ref"].get("maze") is not None:
                ax.axvline(r["ref"]["maze"], color="b", ls=":", label=f"maze-CSV {r['ref']['maze']}")
            ax.set_title(f"{r['name']} — {lbl}")
            ax.set_xlabel("shot"); ax.grid(alpha=.3); ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "task18_highM_maze_vs_atlas.png", dpi=110)
    plt.close(fig)
    # drop the bulky curves from the JSON
    for r in results:
        r.pop("curves", None)
    json.dump(results, open(OUT / "task18_highM_maze_vs_atlas.json", "w"), indent=1, default=float)
    print(f"\nsaved {OUT/'task18_highM_maze_vs_atlas.png'} and .json")


if __name__ == "__main__":
    main()
