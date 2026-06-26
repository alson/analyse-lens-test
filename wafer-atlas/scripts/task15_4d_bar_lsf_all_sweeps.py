"""Task 15 cross-sweep: run atlas-anchored 4D-bar LSF on all 4 anchored sweeps.

For each sweep:
  1. Find which 4D-type instance (col 0, 4, or 8 with row D) is centered
     most-in-frame, given the sweep's anchor-based affine.
  2. Extract bar ROI and run cross_section + lsf_mtf50 per shot.
  3. Plot per-shot MTF50; find argmax.
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
OUT_DIR = Path(__file__).parent.parent / "out" / "task15"

SENSOR_PITCH_UM = 4.35

SWEEPS = [
    {
        "name": "sweep1_M0.385",
        "dir": Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
                    "NIKKOR Z 100-400mm f_4.5-5.6 VR S/1_2.60/F11"),
        "M": 0.385,
        "lsf_ref_shot": 137,
    },
    {
        "name": "sweep2_M1.0",
        "dir": Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
                    "Nikon AF Micro-Nikkor 200mm f_4D IF-ED/1_1/F11"),
        "M": 1.0,
        "lsf_ref_shot": 41,
    },
    {
        "name": "sweep3_M2.0",
        "dir": Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
                    "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001/2_1/F11"),
        "M": 2.0,
        "lsf_ref_shot": 47,
    },
    {
        "name": "sweep4_newer_rig",
        "dir": Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-12/"
                    "NIKKOR Z 24-120mm f_4 S + 61mm extension (2026-05-08_201054)/f_11"),
        "M": None,  # estimated 1.29
        "lsf_ref_shot": None,  # unknown
    },
]


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


def pick_best_4d_instance(atlas, sweep_affine, image_w=8256, image_h=5504):
    """Find the 4D-type instance whose centre is closest to image centre + in-FOV."""
    bar = atlas["die_types"]["(0, 3)"]["feature_inventory"]["slanted_edge"][0]
    u_min, v_min, u_max, v_max = bar["bbox_uv"]
    u_mid = (u_min + u_max) / 2
    v_mid = (v_min + v_max) / 2

    cx_image, cy_image = image_w / 2, image_h / 2
    best = None
    best_dist = float("inf")
    for col_label in [0, 4, 8]:
        row_label = 3  # row D
        cx, cy = die_uv_to_sweep_image(col_label, row_label, u_mid, v_mid,
                                         sweep_affine, atlas)
        # Must be within image with margin for ROI extraction
        margin = 100
        in_fov = (margin < cx < image_w - margin) and (margin < cy < image_h - margin)
        if not in_fov:
            continue
        dist = np.hypot(cx - cx_image, cy - cy_image)
        if dist < best_dist:
            best_dist = dist
            best = {"col_label": col_label, "row_label": row_label,
                    "cx": cx, "cy": cy, "dist_from_centre": dist}
    return best


def run_sweep(sweep_cfg, atlas, sweep_affine):
    print(f"\n{'=' * 70}")
    print(f"=== {sweep_cfg['name']} ===")
    print(f"{'=' * 70}")
    print(f"Affine: θ={sweep_affine['theta_deg']:.3f}° scale={sweep_affine['scale']:.4f}")

    instance = pick_best_4d_instance(atlas, sweep_affine)
    if instance is None:
        print("  No 4D-type instance is centered in the FOV. Skipping.")
        return {"name": sweep_cfg["name"], "skipped": True}
    print(f"Selected instance: col={instance['col_label']}, row={instance['row_label']} "
          f"at ({instance['cx']:.0f}, {instance['cy']:.0f}), "
          f"{instance['dist_from_centre']:.0f} px from image centre")

    bar = atlas["die_types"]["(0, 3)"]["feature_inventory"]["slanted_edge"][0]
    u_min, v_min, u_max, v_max = bar["bbox_uv"]
    col_label, row_label = instance["col_label"], instance["row_label"]

    u_centerline = (u_min + u_max) / 2
    x_bottom, y_bottom = die_uv_to_sweep_image(col_label, row_label, u_centerline, v_min,
                                                 sweep_affine, atlas)
    x_top, y_top = die_uv_to_sweep_image(col_label, row_label, u_centerline, v_max,
                                          sweep_affine, atlas)

    bar_width_px = (u_max - u_min) * sweep_affine["scale"] * atlas["die_pitch_px_in_0129"]["d_col"][col_label % 4]
    bar_height_px = abs(y_top - y_bottom)
    print(f"Bar size in sweep: ~{bar_width_px:.0f} × ~{bar_height_px:.0f} px")

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

    seg = Segment(
        x0=float(x_bottom - roi_x_lo), y0=float(y_bottom - roi_y_lo),
        x1=float(x_top - roi_x_lo), y1=float(y_top - roi_y_lo),
    )
    half_window_px = int(bar_width_px * 0.8)

    shot_paths = sorted(sweep_cfg["dir"].glob("*.jpg")) + sorted(sweep_cfg["dir"].glob("*.JPG"))
    print(f"Shots: {len(shot_paths)}, half_window_px={half_window_px}")

    mtf50_subj = []
    mtf50_sens = []
    peaks = []
    for idx, shot_path in enumerate(shot_paths):
        try:
            img = np.asarray(Image.open(shot_path).convert("L"))
            roi = img[roi_y_lo:min(img.shape[0], roi_y_hi),
                      roi_x_lo:min(img.shape[1], roi_x_hi)]
            if roi.shape[0] < 50 or roi.shape[1] < 50:
                mtf50_subj.append(None); mtf50_sens.append(None); peaks.append(None)
                continue
            profile = cross_section(roi.astype(np.float32), seg, half_window_px=half_window_px)
            m_sens = lsf_mtf50(profile)
            p = lsf_peak_amp(profile)
            peaks.append(p)
            if m_sens is not None and sweep_cfg["M"] is not None:
                m_subj = m_sens * 1000.0 / SENSOR_PITCH_UM * sweep_cfg["M"]
                mtf50_subj.append(m_subj); mtf50_sens.append(m_sens)
            else:
                mtf50_subj.append(None); mtf50_sens.append(m_sens)
        except Exception:
            mtf50_subj.append(None); mtf50_sens.append(None); peaks.append(None)

    # Argmax using mtf50_sens (works for all sweeps regardless of M)
    valid_sens = [(i, m) for i, m in enumerate(mtf50_sens) if m is not None]
    valid_peak = [(i, p) for i, p in enumerate(peaks) if p is not None]
    argmax_sens = max(valid_sens, key=lambda x: x[1]) if valid_sens else (None, None)
    argmax_peak = max(valid_peak, key=lambda x: x[1]) if valid_peak else (None, None)
    print(f"MTF50_sensor argmax: shot {argmax_sens[0]} = {argmax_sens[1]}")
    print(f"Peak amp argmax: shot {argmax_peak[0]} = {argmax_peak[1]}")
    if sweep_cfg.get("lsf_ref_shot") is not None:
        ref = sweep_cfg["lsf_ref_shot"]
        gap = argmax_sens[0] - ref if argmax_sens[0] is not None else None
        print(f"LSF reference shot {ref}, MTF50_sensor argmax gap: {gap:+d}")

    return {
        "name": sweep_cfg["name"],
        "instance_used": instance,
        "bar_size_sweep_px": [float(bar_width_px), float(bar_height_px)],
        "half_window_px": int(half_window_px),
        "M": sweep_cfg["M"],
        "lsf_ref_shot": sweep_cfg["lsf_ref_shot"],
        "mtf50_sensor_per_shot": mtf50_sens,
        "mtf50_subject_per_shot": mtf50_subj,
        "peak_amp_per_shot": peaks,
        "mtf50_sensor_argmax": [argmax_sens[0], argmax_sens[1]],
        "peak_amp_argmax": [argmax_peak[0], argmax_peak[1]],
        "n_shots": len(shot_paths),
    }


def main():
    atlas = json.load(open(ATLAS_PATH))
    anchors = json.load(open(ANCHORS_PATH))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    for sweep_cfg in SWEEPS:
        sweep_affine = anchors.get(sweep_cfg["name"])
        if not sweep_affine:
            print(f"Skipping {sweep_cfg['name']}: no affine in anchors.")
            continue
        r = run_sweep(sweep_cfg, atlas, sweep_affine)
        results.append(r)

    # Combined plot
    fig, axes = plt.subplots(len(results), 1, figsize=(14, 3.5 * len(results)),
                              sharex=False, squeeze=False)
    for i, r in enumerate(results):
        ax = axes[i, 0]
        if r.get("skipped"):
            ax.set_title(f"{r['name']}: skipped (no 4D instance in FOV)")
            continue
        sens = r["mtf50_sensor_per_shot"]
        valid = [(j, m) for j, m in enumerate(sens) if m is not None]
        if valid:
            xs, ys = zip(*valid)
            ax.plot(xs, ys, lw=1.5)
        if r.get("lsf_ref_shot") is not None:
            ax.axvline(r["lsf_ref_shot"], color="green", lw=1, ls="--",
                       alpha=0.6, label=f"LSF ref shot {r['lsf_ref_shot']}")
        if r["mtf50_sensor_argmax"][0] is not None:
            ax.axvline(r["mtf50_sensor_argmax"][0], color="C0", lw=1, ls=":",
                       alpha=0.8, label=f"argmax shot {r['mtf50_sensor_argmax'][0]}")
        ax.set_title(
            f"{r['name']}: 4D-bar slanted-edge MTF50 (via die {r['instance_used']['col_label']}D), "
            f"n_shots={r['n_shots']}"
        )
        ax.set_ylabel("MTF50 sensor (cy/px)")
        ax.legend(loc="lower right", fontsize=8)
        ax.grid(alpha=0.3)
        ax.set_xlabel("Shot index")
    fig.tight_layout()
    out_png = OUT_DIR / "all_sweeps_4d_bar_lsf.png"
    fig.savefig(out_png, dpi=110)
    plt.close(fig)
    print(f"\nSaved combined plot: {out_png}")

    out_json = OUT_DIR / "all_sweeps_4d_bar_lsf.json"
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2,
                  default=lambda o: float(o) if hasattr(o, "__float__") and not isinstance(o, str) else str(o))
    print(f"Saved combined results: {out_json}")

    print(f"\n{'=' * 70}")
    print(f"SUMMARY")
    print(f"{'=' * 70}")
    print(f"{'sweep':<22} {'instance':<10} {'argmax':<8} {'LSF ref':<10} {'gap':<8}")
    for r in results:
        if r.get("skipped"):
            print(f"{r['name']:<22} skipped")
            continue
        inst = f"col {r['instance_used']['col_label']}D"
        argmax_shot = r["mtf50_sensor_argmax"][0]
        ref = r.get("lsf_ref_shot")
        if argmax_shot is not None and ref is not None:
            gap = argmax_shot - ref
            print(f"{r['name']:<22} {inst:<10} {argmax_shot:<8} {ref:<10} {gap:+d}")
        else:
            print(f"{r['name']:<22} {inst:<10} {argmax_shot if argmax_shot is not None else '—':<8} "
                  f"{ref if ref is not None else 'unknown':<10} —")


if __name__ == "__main__":
    sys.exit(main())
