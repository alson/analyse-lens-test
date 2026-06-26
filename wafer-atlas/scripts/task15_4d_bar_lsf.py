"""Task 15: Atlas-anchored 4D-bar slanted-edge LSF measurement on sweep 1.

Approach:
  1. Use sweep 1's anchor-based affine to map the atlas's 4D-bar bbox
     to sweep-1 image coordinates.
  2. Treat the bar's centerline as a "thick scribe" segment.
  3. For each of 142 shots, extract an ROI and call
     tile_sharpness.methods.lsf.cross_section + lsf_mtf50.
  4. Plot per-shot MTF50, find argmax, compare to LSF reference shot 137.

The 4D bar at sweep 1 (M=0.385) should be much better-resolved than scribes:
~62 px wide × ~98 px tall, with two ISOLATED edges far enough apart that
ESF→LSF splits cleanly. The atlas's pixel-precise location avoids any
ROI-search ambiguity that POC A (scribe-based) struggled with.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from tile_sharpness.methods.lsf import Segment, cross_section, lsf_mtf50, lsf_peak_amp


ATLAS_PATH = Path(__file__).parent.parent / "atlas.json"
ANCHORS_PATH = Path(__file__).parent.parent / "out" / "sweep_anchors" / "anchor_fit_params.json"

SWEEP_NAME = "sweep1_M0.385"
SWEEP_DIR = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S/1_2.60/F11"
)
OUT_DIR = Path(__file__).parent.parent / "out" / "task15"

LSF_REFERENCE_SHOT = 137
POC_B_REFERENCE_SHOT = 119

# Z7 pixel pitch
SENSOR_PITCH_UM = 4.35


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
    cl = col_label + u
    rl = row_label + v
    u_c = scale * _cum(d_col, cl)
    v_c = scale * _cum(d_row, rl)
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    return (x0 + cos_t * u_c + sin_t * v_c,
            y0 + sin_t * u_c - cos_t * v_c)


def main():
    atlas = json.load(open(ATLAS_PATH))
    anchors = json.load(open(ANCHORS_PATH))
    sweep_affine = anchors[SWEEP_NAME]
    M = 0.385  # sweep 1 magnification
    print(f"Sweep {SWEEP_NAME}: θ={sweep_affine['theta_deg']:.3f}° "
          f"scale={sweep_affine['scale']:.4f}")

    # Atlas: 4D bar at type (0,3)
    bar = atlas["die_types"]["(0, 3)"]["feature_inventory"]["slanted_edge"][0]
    u_min, v_min, u_max, v_max = bar["bbox_uv"]
    print(f"Atlas 4D bar bbox_uv: [{u_min}, {v_min}] - [{u_max}, {v_max}]")

    # Use die (col=4, row=3) — most central instance
    col_label, row_label = 4, 3

    # Bar center line (vertical in wafer frame, from bottom edge to top edge)
    u_centerline = (u_min + u_max) / 2
    # Centerline endpoints in sweep image
    x_bottom, y_bottom = die_uv_to_sweep_image(col_label, row_label, u_centerline, v_min,
                                                 sweep_affine, atlas)
    x_top, y_top = die_uv_to_sweep_image(col_label, row_label, u_centerline, v_max,
                                          sweep_affine, atlas)
    print(f"4D bar centerline in sweep1: ({x_bottom:.0f}, {y_bottom:.0f}) → ({x_top:.0f}, {y_top:.0f})")

    # Bar size in sweep 1 pixels
    bar_width_px = (u_max - u_min) * sweep_affine["scale"] * atlas["die_pitch_px_in_0129"]["d_col"][col_label % 4]
    bar_height_px = abs(y_top - y_bottom)
    print(f"Bar size: ~{bar_width_px:.0f} px wide × ~{bar_height_px:.0f} px tall")

    # ROI: bbox of the bar with margin
    # Bar corners
    corners_uv = [(u_min, v_min), (u_min, v_max), (u_max, v_min), (u_max, v_max)]
    corners_xy = [die_uv_to_sweep_image(col_label, row_label, u, v, sweep_affine, atlas)
                  for (u, v) in corners_uv]
    xs = [c[0] for c in corners_xy]
    ys = [c[1] for c in corners_xy]
    margin_px = max(40, int(bar_width_px * 1.5))
    roi_x_lo = max(0, int(min(xs) - margin_px))
    roi_x_hi = int(max(xs) + margin_px)
    roi_y_lo = max(0, int(min(ys) - margin_px))
    roi_y_hi = int(max(ys) + margin_px)
    print(f"Bar ROI in sweep1: x=[{roi_x_lo}..{roi_x_hi}] y=[{roi_y_lo}..{roi_y_hi}] "
          f"({roi_x_hi-roi_x_lo}×{roi_y_hi-roi_y_lo})")

    # Centerline segment in ROI coords
    seg_x0 = x_bottom - roi_x_lo
    seg_y0 = y_bottom - roi_y_lo
    seg_x1 = x_top - roi_x_lo
    seg_y1 = y_top - roi_y_lo
    seg = Segment(x0=float(seg_x0), y0=float(seg_y0),
                   x1=float(seg_x1), y1=float(seg_y1))
    print(f"Centerline segment in ROI coords: ({seg.x0:.1f}, {seg.y0:.1f}) → ({seg.x1:.1f}, {seg.y1:.1f})")
    print(f"  length = {seg.length_px:.1f} px, angle = {np.degrees(seg.angle_rad):.2f}°")

    # half_window_px should be > bar_width_px / 2 to capture both edges + margin
    half_window_px = int(bar_width_px * 0.8)
    print(f"Using half_window_px = {half_window_px}")

    # Iterate over shots
    shot_paths = sorted(SWEEP_DIR.glob("*.jpg")) + sorted(SWEEP_DIR.glob("*.JPG"))
    print(f"\n{len(shot_paths)} shots in sweep 1")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    mtf50_subject = []  # per-shot subject MTF50 (lp/mm)
    mtf50_sensor = []   # per-shot sensor MTF50 (cy/px)
    peak_amps = []
    for idx, shot_path in enumerate(shot_paths):
        try:
            img = np.asarray(Image.open(shot_path).convert("L"))
            roi_full = img[roi_y_lo:min(img.shape[0], roi_y_hi),
                            roi_x_lo:min(img.shape[1], roi_x_hi)]
            if roi_full.shape[0] < 50 or roi_full.shape[1] < 50:
                mtf50_subject.append(None)
                mtf50_sensor.append(None)
                peak_amps.append(None)
                continue
            profile = cross_section(roi_full.astype(np.float32), seg,
                                     half_window_px=half_window_px)
            mtf_sensor = lsf_mtf50(profile)
            peak = lsf_peak_amp(profile)
            if mtf_sensor is not None:
                mtf_subj = mtf_sensor * 1000.0 / SENSOR_PITCH_UM * M
                mtf50_subject.append(mtf_subj)
                mtf50_sensor.append(mtf_sensor)
            else:
                mtf50_subject.append(None)
                mtf50_sensor.append(None)
            peak_amps.append(peak)
        except Exception as e:
            mtf50_subject.append(None)
            mtf50_sensor.append(None)
            peak_amps.append(None)
            if idx % 30 == 0:
                print(f"  shot {idx}: error {e}")
        if idx % 30 == 0:
            print(f"  shot {idx}: MTF50_sensor={mtf50_sensor[-1]}, "
                  f"MTF50_subject={mtf50_subject[-1]}, peak={peak_amps[-1]}")

    # Argmax (on MTF50_subject, or peak_amp where MTF50 unavailable)
    valid_mtf = [(i, m) for i, m in enumerate(mtf50_subject) if m is not None]
    valid_peak = [(i, p) for i, p in enumerate(peak_amps) if p is not None]

    if valid_mtf:
        argmax_mtf_idx, argmax_mtf_val = max(valid_mtf, key=lambda x: x[1])
        print(f"\nMTF50_subject argmax: shot {argmax_mtf_idx} = {argmax_mtf_val:.2f} lp/mm")
        print(f"  LSF reference shot {LSF_REFERENCE_SHOT}: MTF50_subject="
              f"{mtf50_subject[LSF_REFERENCE_SHOT]}")
        print(f"  POC B reference shot {POC_B_REFERENCE_SHOT}: MTF50_subject="
              f"{mtf50_subject[POC_B_REFERENCE_SHOT]}")
    if valid_peak:
        argmax_peak_idx, argmax_peak_val = max(valid_peak, key=lambda x: x[1])
        print(f"\nPeak amp argmax: shot {argmax_peak_idx} = {argmax_peak_val:.4f}")
        print(f"  LSF reference shot {LSF_REFERENCE_SHOT}: peak amp={peak_amps[LSF_REFERENCE_SHOT]}")

    # Plot
    fig, ax = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    xs_mtf, ys_mtf = zip(*valid_mtf) if valid_mtf else ([], [])
    ax[0].plot(xs_mtf, ys_mtf, color="C0", lw=1.5, label="MTF50_subject (lp/mm)")
    ax[0].axvline(LSF_REFERENCE_SHOT, color="green", lw=1, ls="--", alpha=0.6,
                  label=f"LSF ref (shot {LSF_REFERENCE_SHOT})")
    ax[0].axvline(POC_B_REFERENCE_SHOT, color="red", lw=1, ls="--", alpha=0.6,
                  label=f"POC B ref (shot {POC_B_REFERENCE_SHOT})")
    if valid_mtf:
        ax[0].axvline(argmax_mtf_idx, color="C0", lw=1, ls=":", alpha=0.8,
                      label=f"argmax (shot {argmax_mtf_idx})")
    ax[0].set_ylabel("MTF50 subject (lp/mm)")
    ax[0].set_title(f"{SWEEP_NAME}: atlas-anchored 4D-bar slanted-edge MTF50 vs shot")
    ax[0].legend(loc="lower right")
    ax[0].grid(alpha=0.3)

    xs_peak, ys_peak = zip(*valid_peak) if valid_peak else ([], [])
    ax[1].plot(xs_peak, ys_peak, color="C1", lw=1.5, label="LSF peak amp")
    ax[1].axvline(LSF_REFERENCE_SHOT, color="green", lw=1, ls="--", alpha=0.6)
    ax[1].axvline(POC_B_REFERENCE_SHOT, color="red", lw=1, ls="--", alpha=0.6)
    if valid_peak:
        ax[1].axvline(argmax_peak_idx, color="C1", lw=1, ls=":", alpha=0.8,
                      label=f"peak argmax (shot {argmax_peak_idx})")
    ax[1].set_xlabel("Shot index")
    ax[1].set_ylabel("LSF peak amp")
    ax[1].legend(loc="lower right")
    ax[1].grid(alpha=0.3)
    fig.tight_layout()
    out_png = OUT_DIR / f"{SWEEP_NAME}_4d_bar_lsf.png"
    fig.savefig(out_png, dpi=110)
    plt.close(fig)
    print(f"\nSaved plot: {out_png}")

    out_json = OUT_DIR / f"{SWEEP_NAME}_4d_bar_lsf.json"
    save_data = {
        "sweep_name": SWEEP_NAME,
        "sweep_affine": sweep_affine,
        "atlas_feature": "4D bar (type (0,3))",
        "bar_bbox_uv": bar["bbox_uv"],
        "die_instance": "4D",
        "bar_width_sweep_px": float(bar_width_px),
        "bar_height_sweep_px": float(bar_height_px),
        "half_window_px": int(half_window_px),
        "mtf50_subject_lpmm_per_shot": mtf50_subject,
        "mtf50_sensor_cypx_per_shot": mtf50_sensor,
        "peak_amp_per_shot": peak_amps,
        "lsf_reference_shot": LSF_REFERENCE_SHOT,
        "pocb_reference_shot": POC_B_REFERENCE_SHOT,
    }
    with open(out_json, "w") as f:
        json.dump(save_data, f, indent=2,
                  default=lambda o: float(o) if hasattr(o, "__float__") and not isinstance(o, str) else str(o))
    print(f"Saved results: {out_json}")


if __name__ == "__main__":
    sys.exit(main())
