"""Unified atlas-anchored focus tool — all magnifications (HANDOVER follow-up #2+#3).

Consolidates the focus-measurement lessons from task17 (low M) and task18 (high M)
into ONE reusable, sweep-agnostic entry point, and adds the per-die field-tilt
map (rig-squareness deliverable).

Core finding it operationalizes: **Laplacian-variance on an atlas-anchored,
deterministically-placed ROI is a single focus-argmax metric that works at EVERY
magnification** — it needs neither usable scribes (LSF) nor M >= 0.7 (the maze
fundamental aliases below that). task17 found it 87% usable at M=0.385; task18
found it 100% usable at M=1.0/2.0, both matching the true LSF focus. The atlas's
contribution is the deterministic ROI (full coverage + per-die location), not the
metric's frequency.

For each sweep it:
  1. registers AUTONOMOUSLY (reg_auto) — zero manual anchors;
  2. projects every in-FOV die to a fixed die-centred ROI;
  3. reads per-shot Laplacian-variance (the universal metric) on each ROI, and
     maze_amp as a cross-check WHERE IT APPLIES (M >= 0.7);
  4. reports the per-die focus argmax, aggregate median/IQR, and the gap vs the
     true LSF centre reference from the tile-sharpness CSV (when available);
  5. FITS A TILT PLANE focus_shot ~ a + bx*x + by*y over the usable dies and
     reports the gradient (shots per 1000 px) — i.e. how far the plane of best
     focus marches across the field, the QR-plate mount squareness.

Usage:  task_atlas_focus.py [sweep_name ...]   (default: all)
Output: out/atlas_focus/<sweep>_focus.json + out/atlas_focus/atlas_focus.png
Run on nufan (full-frame decode x n_shots x n_dies).
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
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
OUT = A / "out" / "atlas_focus"
TS = Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness")
IMAGE_W, IMAGE_H = 8256, 5504
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


reg_auto = _load("reg_auto")
af = _load("anchor_fit_sweep")
ATLAS = json.load(open(A / "atlas.json"))

# M is the subject magnification (drives maze applicability, M>=0.7). None => maze
# skipped (unknown M), lapvar still reported. ref_csv => (path, sweep-key substring).
SWEEPS = {
    "sweep1_M0.385": dict(
        M=0.385, dir=RAW / "2026-01-29/NIKKOR Z 100-400mm f_4.5-5.6 VR S/1_2.60/F11",
        ref_csv=(TS / "out_task2/per_shot_per_tile.csv", "100-400")),
    "sweep2_M1.0": dict(
        M=1.0, dir=RAW / "2026-01-29/Nikon AF Micro-Nikkor 200mm f_4D IF-ED/1_1/F11",
        ref_csv=(TS / "out_apertures_for_calibration/per_shot_per_tile.csv",
                 "200mm_f_4D_IF-ED__1_1__F11")),
    "sweep3_M2.0": dict(
        M=2.0, dir=RAW / "2026-01-29/Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001/2_1/F11",
        ref_csv=(TS / "out_task4/per_shot_per_tile.csv", "TC-2001")),
    "sweep4_newer_rig": dict(
        M=None, dir=RAW / "2026-05-12/NIKKOR Z 24-120mm f_4 S + 61mm extension "
                          "(2026-05-08_201054)/f_11",
        ref_csv=None),
}


def die_uv_to_img(col, row, u, v, p):
    if "k1" in p:
        return reg_auto.grid_xy_distorted(col + u, row + v, p)
    return af.grid_xy(col + u, row + v, p, ATLAS)


def csv_lsf_ref(ref_csv):
    if not ref_csv:
        return None
    path, key = ref_csv
    if not path.exists():
        return None
    by_tile = defaultdict(list)
    with open(path) as f:
        for r in csv.DictReader(f):
            if key in r["sweep"]:
                by_tile[(r["tile_ix"], r["tile_iy"])].append(r)
    centre = by_tile.get(("0", "0")) or next(iter(by_tile.values()), [])
    best = None
    for r in centre:
        try:
            v = float(r["lsf_mtf50_cy_per_px"])
        except (ValueError, KeyError):
            continue
        if v <= 0:
            continue
        si = int(r["shot_idx"])
        if best is None or v > best[1]:
            best = (si, v)
    return best and best[0]


def enumerate_dies(p):
    dies = []
    for col in range(0, 11):
        for row in range(0, 6):
            cx, cy = die_uv_to_img(col, row, 0.5, 0.5, p)
            corners = [die_uv_to_img(col, row, u, v, p) for u, v in ((0, 0), (0, 1), (1, 0), (1, 1))]
            xs = [c[0] for c in corners]; ys = [c[1] for c in corners]
            half = 0.30 * min(max(xs) - min(xs), max(ys) - min(ys))
            if half < 96 or not (half < cx < IMAGE_W - half and half < cy < IMAGE_H - half):
                continue
            dies.append(dict(col=col, row=row, cx=float(cx), cy=float(cy), half=int(half)))
    return dies


def smooth(x, k=7):
    if x.size < k:
        return x
    return np.convolve(np.nan_to_num(x, nan=np.nanmedian(x)), np.ones(k) / k, mode="same")


def focus_stats(arr, n_shots, snr_min=1.8):
    if np.isfinite(arr).sum() < n_shots * 0.8:
        return None
    cs = smooth(arr)
    med = np.nanmedian(arr)
    snr = float(np.nanmax(cs) / med) if med > 0 else 0.0
    return dict(argmax=int(np.nanargmax(cs)), snr=snr, usable=snr >= snr_min)


def fit_tilt_plane(dies, focus, usable):
    """Least-squares focus_shot ~ a + bx*cx + by*cy over usable dies. Returns the
    gradient in shots-per-1000px + residual, or None if too few dies."""
    pts = [(d["cx"], d["cy"], f) for d, f, u in zip(dies, focus, usable) if u and f is not None]
    if len(pts) < 6:
        return None
    X = np.array([[1.0, x, y] for x, y, _ in pts])
    b = np.array([f for _, _, f in pts], float)
    coef, *_ = np.linalg.lstsq(X, b, rcond=None)
    resid = float(np.std(b - X @ coef))
    gx, gy = coef[1] * 1000.0, coef[2] * 1000.0
    return dict(n=len(pts), grad_x_per_kpx=float(gx), grad_y_per_kpx=float(gy),
                grad_mag_per_kpx=float(np.hypot(gx, gy)),
                grad_dir_deg=float(np.degrees(np.arctan2(gy, gx))), resid_shots=resid)


def run_sweep(name):
    cfg = SWEEPS[name]
    M = cfg["M"]
    p = reg_auto.register_and_refine(name)
    if p is None:
        print(f"{name}: reg_auto FAILED"); return None
    dies = enumerate_dies(p)
    shots = sorted(cfg["dir"].glob("*.jpg")) + sorted(cfg["dir"].glob("*.JPG"))
    lsf_ref = csv_lsf_ref(cfg["ref_csv"])
    use_maze = M is not None and M >= 0.7
    print(f"\n{'='*72}\n=== {name} (M={M}) ===  {len(shots)} shots, {len(dies)} in-FOV dies"
          f"  reg fit={p['reg_fit_rmse_px']:.2f}px  maze={'yes' if use_maze else 'no (M<0.7 / unknown)'}"
          f"  LSF ref={lsf_ref}\n{'='*72}")

    lap = {i: [] for i in range(len(dies))}
    mz = {i: [] for i in range(len(dies))}
    for sp in shots:
        img = np.asarray(Image.open(sp).convert("L"))
        for i, d in enumerate(dies):
            hw = d["half"]
            roi = img[int(d["cy"] - hw):int(d["cy"] + hw), int(d["cx"] - hw):int(d["cx"] + hw)]
            if roi.size == 0 or min(roi.shape) < 16:
                lap[i].append(np.nan); mz[i].append(np.nan); continue
            lap[i].append(float(cv2.Laplacian(roi.astype(np.float32), cv2.CV_32F).var()))
            if use_maze:
                v = maze_amp(roi, M)
                mz[i].append(v if v is not None else np.nan)
            else:
                mz[i].append(np.nan)

    lap_focus, lap_usable, maze_focus = [], [], []
    per_die = []
    for i, d in enumerate(dies):
        sl = focus_stats(np.array(lap[i], float), len(shots))
        sm = focus_stats(np.array(mz[i], float), len(shots)) if use_maze else None
        lap_focus.append(sl["argmax"] if sl else None)
        lap_usable.append(bool(sl and sl["usable"]))
        maze_focus.append(sm["argmax"] if sm else None)
        per_die.append(dict(col=d["col"], row=d["row"], cx=d["cx"], cy=d["cy"],
                            lap=sl, maze=sm))

    def agg(focus, usable):
        ams = np.array([f for f, u in zip(focus, usable) if u and f is not None])
        if not ams.size:
            return None
        return dict(usable=int(ams.size), n=len(focus), median=int(np.median(ams)),
                    iqr=[int(np.percentile(ams, 25)), int(np.percentile(ams, 75))],
                    gap_vs_lsf=(int(np.median(ams)) - lsf_ref) if lsf_ref is not None else None)

    lap_agg = agg(lap_focus, lap_usable)
    maze_usable = [bool(per_die[i]["maze"] and per_die[i]["maze"]["usable"]) for i in range(len(dies))]
    maze_agg = agg(maze_focus, maze_usable) if use_maze else None
    tilt = fit_tilt_plane(dies, lap_focus, lap_usable)

    print(f"  lapvar focus: {lap_agg}")
    if maze_agg:
        print(f"  maze  focus: {maze_agg}")
    if tilt:
        print(f"  FIELD TILT (lapvar best-focus plane, n={tilt['n']}): "
              f"{tilt['grad_mag_per_kpx']:.1f} shots/1000px @ {tilt['grad_dir_deg']:+.0f}° "
              f"(x:{tilt['grad_x_per_kpx']:+.1f}, y:{tilt['grad_y_per_kpx']:+.1f}/1000px; "
              f"resid {tilt['resid_shots']:.1f} shots)")
    else:
        print(f"  FIELD TILT: too few usable dies ({sum(lap_usable)}) for a plane fit")
    return dict(name=name, M=M, n_shots=len(shots), n_dies=len(dies), lsf_ref=lsf_ref,
                use_maze=use_maze, reg_fit_rmse_px=p["reg_fit_rmse_px"],
                lapvar=lap_agg, maze=maze_agg, tilt=tilt, per_die=per_die,
                lap_curves={str(i): lap[i] for i in range(len(dies))})


def main():
    names = [a for a in sys.argv[1:] if a in SWEEPS] or list(SWEEPS)
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for name in names:
        r = run_sweep(name)
        if r:
            results.append(r)
            curves = r.pop("lap_curves")
            json.dump(r, open(OUT / f"{name}_focus.json", "w"), indent=1, default=float)
            r["lap_curves"] = curves

    # figure: per-sweep lapvar focus curves (left) + field-tilt scatter (right)
    fig, axes = plt.subplots(len(results), 2, figsize=(15, 4.3 * len(results)), squeeze=False)
    for row, r in enumerate(results):
        axc = axes[row][0]
        for i in r["lap_curves"]:
            arr = np.array(r["lap_curves"][i], float)
            if np.isfinite(arr).sum() < r["n_shots"] * 0.8:
                continue
            cs = smooth(arr); mx = np.nanmax(cs)
            if mx > 0:
                axc.plot(cs / mx, lw=0.7, alpha=0.5)
        if r["lsf_ref"] is not None:
            axc.axvline(r["lsf_ref"], color="g", ls="--", label=f"LSF centre {r['lsf_ref']}")
            axc.legend(fontsize=8)
        axc.set_title(f"{r['name']} (M={r['M']}) — per-die lapvar focus")
        axc.set_xlabel("shot"); axc.grid(alpha=.3)

        axt = axes[row][1]
        pts = [(d["cx"], d["cy"], d["lap"]["argmax"]) for d in r["per_die"]
               if d["lap"] and d["lap"]["usable"]]
        if pts:
            xs, ys, fs = zip(*pts)
            sc = axt.scatter(xs, ys, c=fs, cmap="viridis", s=60, edgecolor="k", lw=0.3)
            fig.colorbar(sc, ax=axt, label="best-focus shot")
        axt.set_xlim(0, IMAGE_W); axt.set_ylim(IMAGE_H, 0)
        ttl = f"{r['name']} — field tilt"
        if r["tilt"]:
            ttl += (f"  {r['tilt']['grad_mag_per_kpx']:.1f} shots/1000px "
                    f"@ {r['tilt']['grad_dir_deg']:+.0f}°")
        axt.set_title(ttl); axt.set_xlabel("image x"); axt.set_ylabel("image y")
    fig.tight_layout()
    fig.savefig(OUT / "atlas_focus.png", dpi=110)
    plt.close(fig)
    print(f"\nsaved {OUT/'atlas_focus.png'} + per-sweep JSON in {OUT}")


if __name__ == "__main__":
    main()
