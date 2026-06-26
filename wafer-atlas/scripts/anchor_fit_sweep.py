"""Solve a per-sweep affine from user anchors + atlas pitch ratios.

Given 3+ user-supplied scribe-intersection anchors and the atlas's wafer-
intrinsic super-cell pitch pattern, fit (theta, x0, y0, scale) by least
squares. Generates a labelled overlay PNG for the user.

This is what we did for 0129; generalised to any sweep.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.optimize import least_squares


ATLAS_PATH = Path(__file__).parent.parent / "atlas.json"
OUT_DIR = Path(__file__).parent.parent / "out" / "sweep_anchors"


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


def _residuals(params, anchors, d_col, d_row):
    theta, x0, y0, scale = params
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    out = []
    for (cl, rl, x_obs, y_obs) in anchors:
        u = scale * _cum(d_col, cl)
        v = scale * _cum(d_row, rl)
        x_pred = x0 + cos_t * u + sin_t * v
        y_pred = y0 + sin_t * u - cos_t * v
        out.append(x_pred - x_obs)
        out.append(y_pred - y_obs)
    return np.array(out)


def fit_sweep_affine(anchors, atlas, theta_init_deg=4.0, scale_init=0.5):
    """Solve (theta, x0, y0, scale) for a sweep from 3+ scribe-intersection anchors.

    anchors: list of (col_line, row_line, x_image, y_image)
    atlas: loaded atlas.json
    """
    d_col = atlas["die_pitch_px_in_0129"]["d_col"]
    d_row = atlas["die_pitch_px_in_0129"]["d_row"]
    theta0 = np.radians(theta_init_deg)
    # Seed x0, y0 from first anchor
    cl0, rl0, x_seed, y_seed = anchors[0]
    u_seed = scale_init * _cum(d_col, cl0)
    v_seed = scale_init * _cum(d_row, rl0)
    x0_init = x_seed - np.cos(theta0) * u_seed - np.sin(theta0) * v_seed
    y0_init = y_seed - np.sin(theta0) * u_seed + np.cos(theta0) * v_seed
    p0 = [theta0, x0_init, y0_init, scale_init]
    sol = least_squares(_residuals, p0, args=(anchors, d_col, d_row), method="lm")
    p = sol.x
    rmse = float(np.sqrt((sol.fun ** 2).mean()))
    return {
        "theta_rad": float(p[0]),
        "theta_deg": float(np.degrees(p[0])),
        "x0_img": float(p[1]),
        "y0_img": float(p[2]),
        "scale": float(p[3]),
        "rmse_px": rmse,
        "d_col_in_sweep": [float(p[3]) * c for c in d_col],
        "d_row_in_sweep": [float(p[3]) * c for c in d_row],
        "super_cell_w_px": float(p[3]) * sum(d_col),
        "super_cell_h_px": float(p[3]) * sum(d_row),
    }


def grid_xy(cl, rl, params, atlas):
    d_col = atlas["die_pitch_px_in_0129"]["d_col"]
    d_row = atlas["die_pitch_px_in_0129"]["d_row"]
    theta = params["theta_rad"]
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    u = params["scale"] * _cum(d_col, cl)
    v = params["scale"] * _cum(d_row, rl)
    return (params["x0_img"] + cos_t * u + sin_t * v,
            params["y0_img"] + sin_t * u - cos_t * v)


def render_overlay(image_path, params, atlas, anchors, out_path,
                   sweep_label, n_col_max=11, n_row_max=6):
    rgb = np.asarray(Image.open(image_path).convert("RGB"))
    H, W = rgb.shape[:2]
    fig, ax = plt.subplots(figsize=(20, 14))
    ax.imshow(rgb)
    d_col = atlas["die_pitch_px_in_0129"]["d_col"]
    d_row = atlas["die_pitch_px_in_0129"]["d_row"]
    wide_col_idx = int(np.argmax(d_col))
    tall_row_idx = int(np.argmax(d_row))
    for cl in range(0, n_col_max + 1):
        is_wide = (cl % 4 == wide_col_idx)
        color = "magenta" if is_wide else "cyan"
        xs, ys = zip(*[grid_xy(cl, rl, params, atlas)
                       for rl in range(0, n_row_max + 1)])
        ax.plot(xs, ys, color=color, lw=0.9, alpha=0.85)
        lx, ly = grid_xy(cl, 0, params, atlas)
        if 0 < lx < W and 0 < ly + 30 < H:
            ax.text(lx, ly + 30, f"c{cl}", color=color, fontsize=11,
                    ha="center", va="top",
                    bbox=dict(boxstyle="round,pad=0.15", fc="black",
                              ec="none", alpha=0.6))
    for rl in range(0, n_row_max + 1):
        is_tall = (rl % 4 == tall_row_idx)
        color = "red" if is_tall else "orange"
        xs, ys = zip(*[grid_xy(cl, rl, params, atlas)
                       for cl in range(0, n_col_max + 1)])
        ax.plot(xs, ys, color=color, lw=0.9, alpha=0.85)
        lx, ly = grid_xy(0, rl, params, atlas)
        if 1 <= rl <= 5:
            label = f"r{rl} ({'ABCDEF'[rl-1]}/{'ABCDEF'[rl]})"
        else:
            label = f"r{rl}"
        if 0 < lx - 30 < W and 0 < ly < H:
            ax.text(lx - 30, ly, label, color=color, fontsize=11,
                    ha="right", va="center",
                    bbox=dict(boxstyle="round,pad=0.15", fc="black",
                              ec="none", alpha=0.6))
    # Die labels in centre
    for col in range(0, n_col_max):
        for row_idx, row_letter in enumerate("ABCDEF"):
            xc, yc = grid_xy(col + 0.5, row_idx + 0.5, params, atlas)
            if 50 < xc < W - 50 and 50 < yc < H - 50:
                ax.text(xc, yc, f"{col}{row_letter}", color="yellow",
                        fontsize=10, ha="center", va="center", alpha=0.8)
    # Anchors
    for (cl, rl, x, y) in anchors:
        ax.plot(x, y, "x", color="lime", markersize=16, markeredgewidth=2.5)
        ax.annotate(f"({cl},{rl})", (x, y), color="lime", fontsize=11,
                    xytext=(10, -10), textcoords="offset points",
                    bbox=dict(boxstyle="round,pad=0.15", fc="black",
                              ec="lime", alpha=0.7))
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.set_title(
        f"{sweep_label}  |  θ={params['theta_deg']:.2f}° CW  "
        f"|  scale={params['scale']:.3f}×  "
        f"|  d_col=[{int(params['d_col_in_sweep'][0])},"
        f"{int(params['d_col_in_sweep'][1])},"
        f"{int(params['d_col_in_sweep'][2])},"
        f"{int(params['d_col_in_sweep'][3])}]px  "
        f"|  RMSE={params['rmse_px']:.2f}px"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


def process_sweep(image_path, anchors, sweep_label, atlas):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"=== {sweep_label} ===")
    print(f"  {image_path}")
    print(f"  {len(anchors)} anchors")
    params = fit_sweep_affine(anchors, atlas, theta_init_deg=4.0, scale_init=0.5)
    print(f"  rotation: {params['theta_deg']:+.3f}° CW")
    print(f"  origin: ({params['x0_img']:.1f}, {params['y0_img']:.1f})")
    print(f"  scale: {params['scale']:.4f}× of atlas (0129)")
    print(f"  d_col_in_sweep: {[f'{x:.0f}' for x in params['d_col_in_sweep']]}")
    print(f"  d_row_in_sweep: {[f'{x:.0f}' for x in params['d_row_in_sweep']]}")
    print(f"  RMSE: {params['rmse_px']:.2f} px")

    overlay = OUT_DIR / f"{sweep_label.replace(' ', '_').replace('/', '_')}.png"
    render_overlay(image_path, params, atlas, anchors, overlay, sweep_label)
    print(f"  → {overlay}")
    return params


def main():
    atlas = json.load(open(ATLAS_PATH))

    # Sweep 1
    sweep1_path = ("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
                   "NIKKOR Z 100-400mm f_4.5-5.6 VR S/1_2.60/F11/"
                   "00296|NIKKOR Z 100-400mm f_4.5-5.6 VR S|1_2.60|400.0 mm|F11|"
                   "alm-20260208-221844-296.jpg")
    sweep1_anchors = [
        (1, 1, 1827, 3548),
        (10, 1, 6078, 3901),
        (6, 5, 4341, 1853),
    ]
    params1 = process_sweep(sweep1_path, sweep1_anchors, "sweep1_M0.385", atlas)

    # Sweep 2
    sweep2_path = ("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
                   "Nikon AF Micro-Nikkor 200mm f_4D IF-ED/1_1/F11/"
                   "00353|Nikon AF Micro-Nikkor 200mm f_4D IF-ED|1_1|200.0 mm|F11|"
                   "alm-20260129-162532-353.jpg")
    sweep2_anchors = [
        (10, 2, 7136, 4742),
        (5, 2, 1012, 4243),
        (8, 5, 4831, 1009),
    ]
    params2 = process_sweep(sweep2_path, sweep2_anchors, "sweep2_M1.0", atlas)

    # Sweep 3: Sigma + TC-2001 @ 2:1 F11 (M ~= 2.0 nominal; effective M from anchors)
    sweep3_path = ("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
                   "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001/2_1/F11/"
                   "04069|Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001|2_1|"
                   "300.0 mm|F11|alm-20260131-001833-1034.jpg")
    sweep3_anchors = [
        (5, 4, 2094, 453),
        (5, 2, 1731, 5238),
        (7, 3, 6696, 3205),
    ]
    params3 = process_sweep(sweep3_path, sweep3_anchors, "sweep3_M2.0", atlas)

    # Sweep 4: Z 24-120 + 61mm extension @ f/11 (newer-rig)
    sweep4_path = ("/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-12/"
                   "NIKKOR Z 24-120mm f_4 S + 61mm extension (2026-05-08_201054)/"
                   "f_11/step_0094_b.jpg")
    sweep4_anchors = [
        (4, 2, 627, 4105),
        (8, 2, 6953, 4605),
        (6, 4, 4166, 1344),
    ]
    params4 = process_sweep(sweep4_path, sweep4_anchors, "sweep4_newer_rig", atlas)

    # Save params
    all_params = {
        "sweep1_M0.385": params1,
        "sweep2_M1.0": params2,
        "sweep3_M2.0": params3,
        "sweep4_newer_rig": params4,
    }
    out_json = OUT_DIR / "anchor_fit_params.json"
    json.dump(all_params, open(out_json, "w"), indent=2)
    print(f"\nSaved params: {out_json}")


if __name__ == "__main__":
    sys.exit(main())
