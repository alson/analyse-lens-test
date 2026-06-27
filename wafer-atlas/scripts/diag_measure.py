"""Task #1 core: atlas-anchored 4D-bar MTF50 with optional PER-SHOT bar
re-detection, to decouple the measurement from focus-rail subject drift.

For a sweep + 4D instance, two measurement modes:
  - "fixed":   the task15 behaviour (one Segment from the affine, used for all shots).
  - "tracked": re-detect the dark bar blob inside the ROI on every shot, place
               the Segment on the detected bar's long axis, size the window to
               the detected bar width.

Reports per-shot MTF50 (sensor) + peak-amp curves and argmax for every in-frame
instance, so we can separate three candidate causes of the sweep-2 gap:
drift (fixed vs tracked), instance/field-curvature (4D vs 8D), focus reference.

Usage: diag_measure.py <sweep_name> [--render]
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

from tile_sharpness.methods.lsf import Segment, cross_section, lsf_mtf50, lsf_peak_amp

_spec = importlib.util.spec_from_file_location(
    "task15", Path(__file__).parent / "task15_4d_bar_lsf_all_sweeps.py")
task15 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(task15)

A = Path(__file__).parent.parent
OUT = A / "out" / "diag_2026_06"
OUT.mkdir(parents=True, exist_ok=True)
atlas = json.load(open(A / "atlas.json"))
anchors = json.load(open(A / "out" / "sweep_anchors" / "anchor_fit_params.json"))
IMAGE_W, IMAGE_H = 8256, 5504
bar = atlas["die_types"]["(0, 3)"]["feature_inventory"]["slanted_edge"][0]
U_MIN, V_MIN, U_MAX, V_MAX = bar["bbox_uv"]


def instance_geometry(aff, col_label):
    """Return predicted bar centre, endpoints, width, ROI box in image coords."""
    row = 3
    u_c = (U_MIN + U_MAX) / 2
    xb, yb = task15.die_uv_to_sweep_image(col_label, row, u_c, V_MIN, aff, atlas)
    xt, yt = task15.die_uv_to_sweep_image(col_label, row, u_c, V_MAX, aff, atlas)
    w_px = (U_MAX - U_MIN) * aff["scale"] * atlas["die_pitch_px_in_0129"]["d_col"][col_label % 4]
    corners = [task15.die_uv_to_sweep_image(col_label, row, u, v, aff, atlas)
               for (u, v) in [(U_MIN, V_MIN), (U_MIN, V_MAX), (U_MAX, V_MIN), (U_MAX, V_MAX)]]
    xs = [c[0] for c in corners]; ys = [c[1] for c in corners]
    margin = max(40, int(w_px * 1.5))
    roi = (max(0, int(min(xs) - margin)), max(0, int(min(ys) - margin)),
           int(max(xs) + margin), int(max(ys) + margin))
    return dict(x_bottom=xb, y_bottom=yb, x_top=xt, y_top=yt, w_px=w_px,
                cx=(min(xs)+max(xs))/2, cy=(min(ys)+max(ys))/2, roi=roi)


def in_frame(geo):
    x0, y0, x1, y1 = geo["roi"]
    return geo["cx"] > 0 and geo["cx"] < IMAGE_W and geo["cy"] > 0 and geo["cy"] < IMAGE_H \
        and (x1 - x0) > 50 and (y1 - y0) > 50


def detect_bar_segment(roi_img, predicted_cx, predicted_cy, expected_w, expected_h):
    """Find the dark bar blob nearest the predicted centre; return (Segment,
    half_window_px) placed on its long axis, or None."""
    g = roi_img.astype(np.uint8)
    # Dark mask via Otsu (bar is dark on lighter field).
    thr, _ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark = (g < thr).astype(np.uint8)
    # Close small gaps so the bar is one solid blob; remove specks.
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lbl, stats, cent = cv2.connectedComponentsWithStats(dark, connectivity=8)
    exp_area = expected_w * expected_h
    best, best_score = None, None
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 0.25 * exp_area or area > 4.0 * exp_area:
            continue
        cxx, cyy = cent[i]
        dist = np.hypot(cxx - predicted_cx, cyy - predicted_cy)
        if dist > 2.0 * max(expected_w, expected_h):
            continue
        # prefer near predicted centre, area close to expected
        score = dist + 0.0005 * abs(area - exp_area)
        if best_score is None or score < best_score:
            best_score, best = score, i
    if best is None:
        return None
    ys, xs = np.where(lbl == best)
    pts = np.column_stack([xs, ys]).astype(np.float32)
    rect = cv2.minAreaRect(pts)  # ((cx,cy),(w,h),angle)
    (rcx, rcy), (rw, rh), ang = rect
    # long axis = the bar's height direction (segment runs along it)
    if rw >= rh:
        long_len, short_len, long_ang = rw, rh, ang
    else:
        long_len, short_len, long_ang = rh, rw, ang + 90.0
    th = np.deg2rad(long_ang)
    ux, uy = np.cos(th), np.sin(th)
    half = long_len * 0.42  # stay off the rounded ends
    seg = Segment(x0=rcx - ux * half, y0=rcy - uy * half,
                  x1=rcx + ux * half, y1=rcy + uy * half)
    half_window = max(12, int(short_len * 0.9))
    return seg, half_window, (rcx, rcy), short_len


def measure(sweep_cfg, aff, col_label, mode, shot_paths):
    geo = instance_geometry(aff, col_label)
    rx0, ry0, rx1, ry1 = geo["roi"]
    bar_w = geo["w_px"]
    bar_h = abs(geo["y_top"] - geo["y_bottom"])
    fixed_seg = Segment(x0=geo["x_bottom"] - rx0, y0=geo["y_bottom"] - ry0,
                        x1=geo["x_top"] - rx0, y1=geo["y_top"] - ry0)
    fixed_hw = int(bar_w * 0.8)
    pred_cx, pred_cy = (geo["cx"] - rx0), (geo["cy"] - ry0)

    mtf, peak, det_off = [], [], []
    for sp in shot_paths:
        try:
            img = np.asarray(Image.open(sp).convert("L"))
            roi = img[ry0:min(img.shape[0], ry1), rx0:min(img.shape[1], rx1)]
            if roi.shape[0] < 50 or roi.shape[1] < 50:
                mtf.append(None); peak.append(None); det_off.append(None); continue
            if mode == "fixed":
                seg, hw = fixed_seg, fixed_hw
                det_off.append(0.0)
            else:
                d = detect_bar_segment(roi, pred_cx, pred_cy, bar_w, bar_h)
                if d is None:
                    mtf.append(None); peak.append(None); det_off.append(None); continue
                seg, hw, (dcx, dcy), _ = d
                det_off.append(float(np.hypot(dcx - pred_cx, dcy - pred_cy)))
            prof = cross_section(roi.astype(np.float32), seg, half_window_px=hw)
            mtf.append(lsf_mtf50(prof)); peak.append(lsf_peak_amp(prof))
        except Exception as e:
            mtf.append(None); peak.append(None); det_off.append(None)
    return dict(col=col_label, mode=mode, mtf=mtf, peak=peak, det_off=det_off,
                bar_w=bar_w, bar_h=bar_h)


def argmax_of(vals):
    v = [(i, x) for i, x in enumerate(vals) if x is not None]
    return max(v, key=lambda t: t[1]) if v else (None, None)


def main():
    name = sys.argv[1]
    render = "--render" in sys.argv
    cfg = {c["name"]: c for c in task15.SWEEPS}[name]
    aff = anchors[name]
    shot_paths = sorted(cfg["dir"].glob("*.jpg")) + sorted(cfg["dir"].glob("*.JPG"))
    print(f"{name}: {len(shot_paths)} shots, ref={cfg['lsf_ref_shot']}")

    cols = [c for c in (0, 4, 8) if in_frame(instance_geometry(aff, c))]
    print(f"in-frame instances: {[f'{c}D' for c in cols]}")

    results = []
    for col in cols:
        for mode in ("fixed", "tracked"):
            r = measure(cfg, aff, col, mode, shot_paths)
            am_m = argmax_of(r["mtf"]); am_p = argmax_of(r["peak"])
            r["argmax_mtf"] = am_m; r["argmax_peak"] = am_p
            nvalid = sum(x is not None for x in r["mtf"])
            ref = cfg["lsf_ref_shot"]
            gap = (am_m[0] - ref) if (am_m[0] is not None and ref is not None) else None
            offs = [o for o in r["det_off"] if o is not None]
            print(f"  col {col}D {mode:8s}: MTF50 argmax shot {am_m[0]} "
                  f"(gap {gap:+d})" if gap is not None else
                  f"  col {col}D {mode:8s}: MTF50 argmax shot {am_m[0]} (gap n/a)", end="")
            print(f"  peakargmax {am_p[0]}  nvalid={nvalid}/{len(shot_paths)}"
                  f"  det_off med={np.median(offs):.0f}px" if offs else
                  f"  peakargmax {am_p[0]}  nvalid={nvalid}/{len(shot_paths)}")
            results.append(r)

    # plot
    fig, axes = plt.subplots(len(cols), 1, figsize=(13, 3.2 * len(cols)), squeeze=False)
    for ax, col in zip(axes[:, 0], cols):
        for r in results:
            if r["col"] != col:
                continue
            v = [(i, m) for i, m in enumerate(r["mtf"]) if m is not None]
            if v:
                xs, ys = zip(*v)
                ax.plot(xs, ys, lw=1.3, label=f"{r['mode']} (argmax {r['argmax_mtf'][0]})")
        if cfg["lsf_ref_shot"] is not None:
            ax.axvline(cfg["lsf_ref_shot"], color="green", ls="--", alpha=0.6,
                       label=f"LSF ref {cfg['lsf_ref_shot']}")
        ax.set_title(f"{name} col {col}D — MTF50 sensor per shot")
        ax.set_xlabel("shot"); ax.set_ylabel("MTF50 (cy/px)")
        ax.grid(alpha=0.3); ax.legend(fontsize=8)
    fig.tight_layout()
    p = OUT / f"{name}_measure.png"
    fig.savefig(p, dpi=110); plt.close(fig)
    print(f"saved {p}")

    with open(OUT / f"{name}_measure.json", "w") as f:
        json.dump([{k: (v if k not in ("mtf", "peak", "det_off") else v)
                    for k, v in r.items()} for r in results], f, indent=1, default=float)


if __name__ == "__main__":
    main()
