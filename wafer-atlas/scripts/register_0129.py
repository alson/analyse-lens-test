"""Register prev_step_0129_b.jpg to atlas coords + re-extract dies at higher res.

The 0129 photo (NIKKOR Z 100-400 + 35mm extension, f/11) has higher
magnification than the f/8 overview (step_0131_c). We assume the wafer's
super-cell pitch ratios are invariant (it's the same physical wafer), so
we only need to solve per-photo (theta, x0, y0, scale) — 4 unknowns from
3 user anchors (6 equations).

Anchors in 0129 (col_line, row_line, x_image, y_image):
  c1, r1   → (269, 4020)
  c11, r5  → (7971, 1675)
  c10, r1  → (6987, 4619)

Reference super-cell (from grid_supercell_refined.py on the overview):
  d_col_overview = [539.02, 457.54, 453.95, 453.24]
  d_row_overview = [455.88, 543.88, 452.83, 452.19]

Output:
  - JSON with the new photo's grid params
  - Overlay PNG showing the predicted grid on 0129
  - Per-die crops at higher resolution (OUT_SIZE=900) for 4D / 3E / 3C
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates
from scipy.optimize import least_squares


PHOTO_PATH = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-13/"
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S + 35mm extension/f_11/prev_step_0129_b.jpg"
)
OUT_DIR = Path(__file__).parent.parent / "out" / "0129"

D_COL_OVERVIEW = np.array([539.02, 457.54, 453.95, 453.24])
D_ROW_OVERVIEW = np.array([455.88, 543.88, 452.83, 452.19])

ANCHORS = [
    (1, 1, 269, 4020),
    (11, 5, 7971, 1675),
    (10, 1, 6987, 4619),
]

OUT_SIZE = 900   # px per die in extracted crop (higher than overview's 600)
MARGIN = 0.05


def _cum(d4, k):
    if k <= 0:
        return 0.0
    k_int = int(np.floor(k))
    frac = k - k_int
    full = k_int // 4
    rem = k_int % 4
    c = full * d4.sum() + d4[:rem].sum()
    if frac > 0:
        c += frac * d4[rem]
    return c


def _residuals(params, anchors):
    """params = (theta, x0, y0, scale). d_col/d_row inherit ratios from overview."""
    theta, x0, y0, scale = params
    d_col = scale * D_COL_OVERVIEW
    d_row = scale * D_ROW_OVERVIEW
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    res = []
    for (cl, rl, x_obs, y_obs) in anchors:
        u = _cum(d_col, cl)
        v = _cum(d_row, rl)
        x_pred = x0 + cos_t * u + sin_t * v
        y_pred = y0 + sin_t * u - cos_t * v
        res.append(x_pred - x_obs)
        res.append(y_pred - y_obs)
    return np.array(res)


def solve_grid():
    # Initial guess from the analytic 2-anchor fit
    p0 = [np.radians(5.0), -700.0, 4700.0, 1.58]
    sol = least_squares(_residuals, p0, args=(ANCHORS,), method="lm")
    p = sol.x
    rmse = float(np.sqrt((sol.fun ** 2).mean()))
    return {
        "theta_rad": float(p[0]),
        "theta_deg": float(np.degrees(p[0])),
        "x0": float(p[1]),
        "y0": float(p[2]),
        "scale": float(p[3]),
        "d_col": (p[3] * D_COL_OVERVIEW).tolist(),
        "d_row": (p[3] * D_ROW_OVERVIEW).tolist(),
        "rmse_px": rmse,
        "residuals": sol.fun.tolist(),
    }


def grid_xy(cl, rl, params):
    theta = params["theta_rad"]
    x0, y0 = params["x0"], params["y0"]
    d_col = np.array(params["d_col"])
    d_row = np.array(params["d_row"])
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    u = _cum(d_col, cl)
    v = _cum(d_row, rl)
    return (x0 + cos_t * u + sin_t * v,
            y0 + sin_t * u - cos_t * v)


def extract_die_crop(image, cl_label, rl_label, params,
                     out_size=OUT_SIZE, margin=MARGIN):
    theta = params["theta_rad"]
    x0, y0 = params["x0"], params["y0"]
    d_col = np.array(params["d_col"])
    d_row = np.array(params["d_row"])
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    base_u = _cum(d_col, cl_label)
    base_v = _cum(d_row, rl_label)
    du = d_col[cl_label % 4]
    dv = d_row[rl_label % 4]
    u_range = np.linspace(-margin, 1 + margin, out_size)
    v_range = np.linspace(1 + margin, -margin, out_size)
    U, V = np.meshgrid(u_range, v_range)
    u_cum = base_u + U * du
    v_cum = base_v + V * dv
    x_image = x0 + cos_t * u_cum + sin_t * v_cum
    y_image = y0 + sin_t * u_cum - cos_t * v_cum
    coords = np.stack([y_image.ravel(), x_image.ravel()])
    sampled = map_coordinates(image, coords, order=1, mode="nearest")
    return sampled.reshape(out_size, out_size).astype(np.float32)


def overlay_grid(rgb, params, out_path):
    H, W = rgb.shape[:2]
    fig, ax = plt.subplots(figsize=(20, 14))
    ax.imshow(rgb.astype(np.uint8))
    d_col = np.array(params["d_col"])
    d_row = np.array(params["d_row"])
    for cl in range(0, 12):
        is_wide = (cl % 4 == int(np.argmax(d_col)))
        color = "magenta" if is_wide else "cyan"
        xs, ys = zip(*[grid_xy(cl, rl, params) for rl in range(0, 7)])
        ax.plot(xs, ys, color=color, lw=0.9, alpha=0.85)
        x_lbl, y_lbl = grid_xy(cl, 0, params)
        if 0 < x_lbl < W and 0 < y_lbl + 30 < H:
            ax.text(x_lbl, y_lbl + 30, f"c{cl}", color=color, fontsize=10,
                    ha="center", va="top",
                    bbox=dict(boxstyle="round,pad=0.15", fc="black",
                              ec="none", alpha=0.5))
    for rl in range(0, 7):
        is_tall = (rl % 4 == int(np.argmax(d_row)))
        color = "red" if is_tall else "orange"
        xs, ys = zip(*[grid_xy(cl, rl, params) for cl in range(0, 12)])
        ax.plot(xs, ys, color=color, lw=0.9, alpha=0.85)
        x_lbl, y_lbl = grid_xy(0, rl, params)
        if 1 <= rl <= 5:
            label = f"r{rl} ({'ABCDEF'[rl-1]}/{'ABCDEF'[rl]})"
        else:
            label = f"r{rl}"
        if 0 < x_lbl - 30 < W and 0 < y_lbl < H:
            ax.text(x_lbl - 30, y_lbl, label, color=color, fontsize=10,
                    ha="right", va="center",
                    bbox=dict(boxstyle="round,pad=0.15", fc="black",
                              ec="none", alpha=0.5))
    for (cl, rl, x, y) in ANCHORS:
        ax.plot(x, y, "x", color="lime", markersize=14, markeredgewidth=2)
        ax.annotate(f"(c{cl},r{rl})", (x, y), color="lime", fontsize=10,
                    xytext=(8, -8), textcoords="offset points",
                    bbox=dict(boxstyle="round,pad=0.15", fc="black",
                              ec="lime", alpha=0.65))
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.set_title(
        f"0129 grid  |  θ={params['theta_deg']:.2f}° CW  "
        f"|  scale={params['scale']:.3f}×  "
        f"|  d_col=[{int(params['d_col'][0])},{int(params['d_col'][1])},"
        f"{int(params['d_col'][2])},{int(params['d_col'][3])}]px  "
        f"|  RMSE={params['rmse_px']:.2f}px"
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


def main():
    rgb = np.asarray(Image.open(PHOTO_PATH).convert("RGB"), dtype=np.float32)
    gray = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1]
            + 0.114 * rgb[..., 2]).astype(np.float32)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    params = solve_grid()
    print("Grid params for 0129:")
    print(f"  rotation: {params['theta_deg']:.3f}° CW")
    print(f"  origin:   ({params['x0']:.1f}, {params['y0']:.1f})")
    print(f"  scale vs overview: {params['scale']:.4f}×")
    print(f"  d_col: {params['d_col']}")
    print(f"  d_row: {params['d_row']}")
    print(f"  super-cell width: {sum(params['d_col']):.1f} px")
    print(f"  super-cell height: {sum(params['d_row']):.1f} px")
    print(f"  RMSE: {params['rmse_px']:.2f} px ({len(ANCHORS)} anchors)")
    print(f"  per-anchor residuals: {params['residuals']}")

    # Save params
    with open(OUT_DIR / "grid_params.json", "w") as f:
        json.dump(params, f, indent=2)
    print(f"\nSaved: {OUT_DIR / 'grid_params.json'}")

    # Overlay
    overlay_path = OUT_DIR / "grid_overlay.png"
    overlay_grid(rgb, params, overlay_path)
    print(f"Saved: {overlay_path}")

    # Extract die crops for the top-3
    targets = [(4, 3, "4D"), (3, 4, "3E"), (3, 2, "3C")]
    for cl, rl, label in targets:
        crop = extract_die_crop(gray, cl, rl, params)
        out_path = OUT_DIR / f"die_{label}_crop.png"
        Image.fromarray(crop.clip(0, 255).astype(np.uint8)).save(out_path)
        print(f"  Saved die {label} crop: {out_path} (out_size={OUT_SIZE})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
