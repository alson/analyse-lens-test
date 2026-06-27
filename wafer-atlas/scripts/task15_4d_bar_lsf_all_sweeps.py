"""Atlas-anchored 4D-bar focus measurement across all anchored sweeps.

CANONICAL corrected version (2026-06-27). Supersedes the original which had two
bugs (see REPORT_2026-06-27.md):

  1. FOCUS METRIC. The original took the focus argmax from ``lsf_mtf50``, but at
     M>=1.0 the 4D bar's MTF50 SATURATES (flat-tops ~0.337 cy/px) over the
     in-focus region, so the argmax was degenerate. We take the focus argmax
     from a NON-SATURATING metric (Laplacian variance on the per-shot-tracked
     bar box) and report ``lsf_mtf50`` only as the absolute-resolution readout
     at the focus shot.

  2. REFERENCE. The original ``lsf_ref_shot`` values (137/41/47) were actually
     JPEG-FILESIZE argmaxes, not LSF focus argmaxes. We pull the TRUE
     ``lsf_mtf50`` and ``maze_fft_amp`` centre-tile argmaxes from the
     tile-sharpness per-shot CSVs and report filesize separately for contrast.

Per-shot bar tracking removes focus-rail subject drift; measuring every in-frame
4D instance exposes the field-focus TILT (best-focus shot varies with field x).

Output: out/task15/all_sweeps_4d_bar_lsf.{png,json} + printed summary.
"""
from __future__ import annotations

import csv
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

from tile_sharpness.methods.lsf import Segment, cross_section, lsf_mtf50, lsf_peak_amp


ATLAS_PATH = Path(__file__).parent.parent / "atlas.json"
ANCHORS_PATH = Path(__file__).parent.parent / "out" / "sweep_anchors" / "anchor_fit_params.json"
OUT_DIR = Path(__file__).parent.parent / "out" / "task15"
TS = Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness")

SENSOR_PITCH_UM = 4.35
IMAGE_W, IMAGE_H = 8256, 5504

SWEEPS = [
    {
        "name": "sweep1_M0.385",
        "dir": Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
                    "NIKKOR Z 100-400mm f_4.5-5.6 VR S/1_2.60/F11"),
        "M": 0.385,
        # true focus reference is pulled from the tile-sharpness per-shot CSV:
        "ref_csv": (TS / "out_task2/per_shot_per_tile.csv", "100-400"),
    },
    {
        "name": "sweep2_M1.0",
        "dir": Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
                    "Nikon AF Micro-Nikkor 200mm f_4D IF-ED/1_1/F11"),
        "M": 1.0,
        "ref_csv": (TS / "out_apertures_for_calibration/per_shot_per_tile.csv",
                    "200mm_f_4D_IF-ED__1_1__F11"),
    },
    {
        "name": "sweep3_M2.0",
        "dir": Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
                    "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001/2_1/F11"),
        "M": 2.0,
        "ref_csv": (TS / "out_task4/per_shot_per_tile.csv", "TC-2001"),
    },
    {
        "name": "sweep4_newer_rig",
        "dir": Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-12/"
                    "NIKKOR Z 24-120mm f_4 S + 61mm extension (2026-05-08_201054)/f_11"),
        "M": None,        # estimated 1.29
        "ref_csv": None,  # newer rig — not in the tile-sharpness CSVs
    },
]


# --------------------------------------------------------------------------
# Geometry (also imported by diag_measure.py — keep signatures stable)
# --------------------------------------------------------------------------
def _cum(d4, k):
    if k <= 0:
        return 0.0
    k_int = int(np.floor(k))
    frac = k - k_int
    full = k_int // 4
    rem = k_int % 4
    c = full * sum(d4) + sum(d4[:rem])
    if frac > 0:
        c += frac * d4[rem]
    return c


def die_uv_to_sweep_image(col_label, row_label, u, v, sweep_affine, atlas):
    d_col = atlas["die_pitch_px_in_0129"]["d_col"]
    d_row = atlas["die_pitch_px_in_0129"]["d_row"]
    theta = sweep_affine["theta_rad"]
    x0, y0 = sweep_affine["x0_img"], sweep_affine["y0_img"]
    scale = sweep_affine["scale"]
    u_c = scale * _cum(d_col, col_label + u)
    v_c = scale * _cum(d_row, row_label + v)
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    return (x0 + cos_t * u_c + sin_t * v_c,
            y0 + sin_t * u_c - cos_t * v_c)


def _in_frame_instances(atlas, aff):
    """Return the col labels (0/4/8) whose 4D-bar centre is in the FOV."""
    bar = atlas["die_types"]["(0, 3)"]["feature_inventory"]["slanted_edge"][0]
    u_min, v_min, u_max, v_max = bar["bbox_uv"]
    cols = []
    for col in (0, 4, 8):
        cx, cy = die_uv_to_sweep_image(col, 3, (u_min + u_max) / 2, (v_min + v_max) / 2, aff, atlas)
        if 100 < cx < IMAGE_W - 100 and 100 < cy < IMAGE_H - 100:
            cols.append(col)
    return cols


def pick_best_4d_instance(atlas, sweep_affine, image_w=IMAGE_W, image_h=IMAGE_H):
    """Kept for backward-compat (diag scripts). The most-central in-FOV 4D instance."""
    bar = atlas["die_types"]["(0, 3)"]["feature_inventory"]["slanted_edge"][0]
    u_min, v_min, u_max, v_max = bar["bbox_uv"]
    u_mid, v_mid = (u_min + u_max) / 2, (v_min + v_max) / 2
    best, best_d = None, float("inf")
    for col in (0, 4, 8):
        cx, cy = die_uv_to_sweep_image(col, 3, u_mid, v_mid, sweep_affine, atlas)
        if not (100 < cx < image_w - 100 and 100 < cy < image_h - 100):
            continue
        d = np.hypot(cx - image_w / 2, cy - image_h / 2)
        if d < best_d:
            best_d, best = d, {"col_label": col, "row_label": 3, "cx": cx, "cy": cy,
                               "dist_from_centre": d}
    return best


# --------------------------------------------------------------------------
# Per-shot bar tracking + focus metrics
# --------------------------------------------------------------------------
def instance_geometry(atlas, aff, col):
    bar = atlas["die_types"]["(0, 3)"]["feature_inventory"]["slanted_edge"][0]
    u_min, v_min, u_max, v_max = bar["bbox_uv"]
    u_c = (u_min + u_max) / 2
    xb, yb = die_uv_to_sweep_image(col, 3, u_c, v_min, aff, atlas)
    xt, yt = die_uv_to_sweep_image(col, 3, u_c, v_max, aff, atlas)
    w_px = (u_max - u_min) * aff["scale"] * atlas["die_pitch_px_in_0129"]["d_col"][col % 4]
    corners = [die_uv_to_sweep_image(col, 3, u, v, aff, atlas)
               for (u, v) in [(u_min, v_min), (u_min, v_max), (u_max, v_min), (u_max, v_max)]]
    xs = [c[0] for c in corners]; ys = [c[1] for c in corners]
    margin = max(40, int(w_px * 1.5))
    roi = (max(0, int(min(xs) - margin)), max(0, int(min(ys) - margin)),
           int(max(xs) + margin), int(max(ys) + margin))
    return dict(w_px=w_px, h_px=abs(yt - yb), cx=(min(xs) + max(xs)) / 2,
                cy=(min(ys) + max(ys)) / 2, roi=roi)


def detect_bar_segment(roi_img, pred_cx, pred_cy, exp_w, exp_h):
    """Dark-bar blob nearest the predicted centre -> (Segment, half_window, (cx,cy))."""
    g = roi_img.astype(np.uint8)
    thr, _ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark = cv2.morphologyEx((g < thr).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lbl, stats, cent = cv2.connectedComponentsWithStats(dark, 8)
    exp_area = exp_w * exp_h
    best, best_score = None, None
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 0.25 * exp_area or area > 4.0 * exp_area:
            continue
        cxx, cyy = cent[i]
        dist = np.hypot(cxx - pred_cx, cyy - pred_cy)
        if dist > 2.0 * max(exp_w, exp_h):
            continue
        score = dist + 0.0005 * abs(area - exp_area)
        if best_score is None or score < best_score:
            best_score, best = score, i
    if best is None:
        return None
    ys, xs = np.where(lbl == best)
    rect = cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32))
    (rcx, rcy), (rw, rh), ang = rect
    long_len, short_len, long_ang = (rw, rh, ang) if rw >= rh else (rh, rw, ang + 90.0)
    th = np.deg2rad(long_ang)
    ux, uy = np.cos(th), np.sin(th)
    half = long_len * 0.42
    seg = Segment(x0=rcx - ux * half, y0=rcy - uy * half, x1=rcx + ux * half, y1=rcy + uy * half)
    return seg, max(12, int(short_len * 0.9)), (rcx, rcy)


def csv_reference(ref_csv):
    """True centre-tile focus argmaxes from the tile-sharpness per-shot CSV."""
    if not ref_csv:
        return {}
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
    return {"lsf": am("lsf_mtf50_cy_per_px"), "maze": am("maze_fft_amp"),
            "filesize": am("filesize_bytes")}


def run_sweep(cfg, atlas, aff):
    name = cfg["name"]
    cols = _in_frame_instances(atlas, aff)
    shots = sorted(cfg["dir"].glob("*.jpg")) + sorted(cfg["dir"].glob("*.JPG"))
    ref = csv_reference(cfg.get("ref_csv"))
    print(f"\n{'=' * 70}\n=== {name} ===  {len(shots)} shots, in-frame {cols}\n{'=' * 70}")
    print(f"true LSF-centre ref={ref.get('lsf')}  maze={ref.get('maze')}  "
          f"filesize(NOT a focus ref)={ref.get('filesize')}")

    instances = []
    for col in cols:
        geo = instance_geometry(atlas, aff, col)
        rx0, ry0, rx1, ry1 = geo["roi"]
        bw, bh = geo["w_px"], geo["h_px"]
        pred_cx, pred_cy = geo["cx"] - rx0, geo["cy"] - ry0
        half = int(max(bw, bh) * 0.7)
        lap, mtf = [], []
        for sp in shots:
            img = np.asarray(Image.open(sp).convert("L"))
            roi = img[ry0:min(img.shape[0], ry1), rx0:min(img.shape[1], rx1)]
            d = detect_bar_segment(roi, pred_cx, pred_cy, bw, bh) if roi.size and min(roi.shape) > 8 else None
            if d is None:
                lap.append(np.nan); mtf.append(np.nan); continue
            seg, hw, (dcx, dcy) = d
            y0 = max(0, int(dcy - half)); y1 = min(roi.shape[0], int(dcy + half))
            x0 = max(0, int(dcx - half)); x1 = min(roi.shape[1], int(dcx + half))
            box = roi[y0:y1, x0:x1].astype(np.float32)
            lap.append(float(cv2.Laplacian(box, cv2.CV_32F).var()) if box.size else np.nan)
            m = lsf_mtf50(cross_section(roi.astype(np.float32), seg, half_window_px=hw))
            mtf.append(m if m is not None else np.nan)
        lap = np.array(lap, float); mtf = np.array(mtf, float)
        focus = int(np.nanargmax(lap)) if not np.all(np.isnan(lap)) else None
        mtf_sat = int(np.nanargmax(mtf)) if not np.all(np.isnan(mtf)) else None
        instances.append(dict(col=col, cx=geo["cx"], focus_shot=focus,
                              mtf50_argmax_saturating=mtf_sat,
                              mtf50_at_focus=(float(mtf[focus]) if focus is not None and not np.isnan(mtf[focus]) else None),
                              lapvar=lap.tolist(), mtf50=mtf.tolist()))
        gap = (focus - ref["lsf"]) if (focus is not None and ref.get("lsf") is not None) else None
        print(f"  {col}D (x={geo['cx']:.0f}): focus_shot(lapvar)={focus} "
              f"(gap vs LSF {gap:+d})" if gap is not None else
              f"  {col}D (x={geo['cx']:.0f}): focus_shot(lapvar)={focus} (no CSV ref)", end="")
        print(f"  [mtf50 argmax(saturating)={mtf_sat}, mtf50@focus={instances[-1]['mtf50_at_focus']}]")
    return dict(name=name, n_shots=len(shots), ref=ref, instances=instances)


def main():
    atlas = json.load(open(ATLAS_PATH))
    anchors = json.load(open(ANCHORS_PATH))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    for cfg in SWEEPS:
        aff = anchors.get(cfg["name"])
        if not aff:
            print(f"skip {cfg['name']}: no affine")
            continue
        results.append(run_sweep(cfg, atlas, aff))

    # plot per-sweep lapvar focus curves (normalized) with the true ref
    fig, axes = plt.subplots(len(results), 1, figsize=(14, 3.2 * len(results)), squeeze=False)
    for ax, r in zip(axes[:, 0], results):
        for it in r["instances"]:
            lap = np.array(it["lapvar"], float)
            if np.all(np.isnan(lap)):
                continue
            ax.plot(lap / np.nanmax(lap), lw=1.3, label=f"{it['col']}D focus={it['focus_shot']}")
        if r["ref"].get("lsf") is not None:
            ax.axvline(r["ref"]["lsf"], color="g", ls="--", alpha=.7, label=f"true LSF centre {r['ref']['lsf']}")
        if r["ref"].get("filesize") is not None:
            ax.axvline(r["ref"]["filesize"], color="r", ls=":", alpha=.6, label=f"filesize (not focus) {r['ref']['filesize']}")
        ax.set_title(f"{r['name']} — atlas-anchored 4D-bar focus (lapvar, normalized)")
        ax.set_xlabel("shot"); ax.set_ylabel("lapvar/max"); ax.grid(alpha=.3); ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "all_sweeps_4d_bar_lsf.png", dpi=110)
    plt.close(fig)
    json.dump(results, open(OUT_DIR / "all_sweeps_4d_bar_lsf.json", "w"), indent=2, default=float)

    print(f"\n{'=' * 70}\nSUMMARY (focus argmax = non-saturating lapvar)\n{'=' * 70}")
    print(f"{'sweep':<18}{'instance':<10}{'focus':<7}{'LSF ref':<9}{'gap':<6}{'maze':<6}{'filesize*':<10}")
    for r in results:
        ref = r["ref"]
        for it in r["instances"]:
            gap = (it["focus_shot"] - ref["lsf"]) if (it["focus_shot"] is not None and ref.get("lsf") is not None) else None
            print(f"{r['name']:<18}{str(it['col'])+'D':<10}{str(it['focus_shot']):<7}"
                  f"{str(ref.get('lsf')):<9}{(f'{gap:+d}' if gap is not None else '-'):<6}"
                  f"{str(ref.get('maze')):<6}{str(ref.get('filesize')):<10}")
    print("* filesize argmax is NOT a focus reference (was the original bug); shown for contrast.")


if __name__ == "__main__":
    sys.exit(main())
