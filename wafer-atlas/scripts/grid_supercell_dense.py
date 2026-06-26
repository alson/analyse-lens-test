"""Dense CV anchor sampling + super-cell refit.

Predicts every grid intersection (cl, rl) for cl ∈ 0..11, rl ∈ 0..6, runs
CV snap-to-scribe at each, screens by quality (local-min depth, position
within search window), and refits the super-cell model with the kept
anchors. Reports per-line scribe-position errors so we can see if the
remaining residuals reveal a non-4-periodic structure.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.optimize import least_squares


PHOTO_PATH = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-13/"
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S/f_8/step_0131_c.jpg"
)
OUT_DIR = Path(__file__).parent.parent / "out"

# Starting model from grid_supercell_refined.py
INIT_THETA_DEG = 4.665
INIT_X0, INIT_Y0 = 1063.9, 4028.6
INIT_D_COL = np.array([539.02, 457.54, 453.95, 453.24])
INIT_D_ROW = np.array([455.88, 543.88, 452.83, 452.19])

SEARCH_RADIUS = 28
STRIP_HALF_LENGTH = 60
MIN_DEPTH_RATIO = 0.93   # accept anchor only if intensity_min < 0.93 * intensity_mean
MAX_EDGE_FRAC = 0.85     # reject anchors whose best offset is in the outer 15 %


def _cum(d4: np.ndarray, k: float) -> float:
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


def grid_xy(cl, rl, theta, x0, y0, d_col, d_row):
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    u = _cum(d_col, cl)
    v = _cum(d_row, rl)
    return (x0 + cos_t * u + sin_t * v,
            y0 + sin_t * u - cos_t * v)


def _residuals(params, anchors):
    theta, x0, y0 = params[0], params[1], params[2]
    d_col = params[3:7]
    d_row = params[7:11]
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    res = []
    for (cl, rl, x_obs, y_obs, _w) in anchors:
        u = _cum(d_col, cl)
        v = _cum(d_row, rl)
        x_pred = x0 + cos_t * u + sin_t * v
        y_pred = y0 + sin_t * u - cos_t * v
        res.append(x_pred - x_obs)
        res.append(y_pred - y_obs)
    return np.array(res)


def _sample_strip(image, x_centre, y_centre, direction, half_length):
    s = np.arange(-half_length, half_length + 1, dtype=np.float64)
    xs = x_centre + s * direction[0]
    ys = y_centre + s * direction[1]
    H, W = image.shape
    xs_int = np.clip(np.round(xs).astype(int), 0, W - 1)
    ys_int = np.clip(np.round(ys).astype(int), 0, H - 1)
    return float(image[ys_int, xs_int].mean())


def refine_with_quality(image, x_init, y_init, theta_rad,
                        search_radius=SEARCH_RADIUS,
                        strip_half_length=STRIP_HALF_LENGTH):
    """Refine and return (x, y, quality) where quality ∈ [0, 1]."""
    cos_t = np.cos(theta_rad)
    sin_t = np.sin(theta_rad)
    v_dir = (sin_t, -cos_t)
    h_dir = (cos_t, sin_t)
    offsets = np.arange(-search_radius, search_radius + 1)

    intens_x = np.array([
        _sample_strip(image, x_init + d * cos_t, y_init + d * sin_t,
                      v_dir, strip_half_length)
        for d in offsets
    ])
    min_idx_x = int(np.argmin(intens_x))
    best_d_x = offsets[min_idx_x]
    x_refined = x_init + best_d_x * cos_t
    y_after_x = y_init + best_d_x * sin_t

    intens_y = np.array([
        _sample_strip(image, x_refined + d * sin_t, y_after_x - d * cos_t,
                      h_dir, strip_half_length)
        for d in offsets
    ])
    min_idx_y = int(np.argmin(intens_y))
    best_d_y = offsets[min_idx_y]
    x_final = x_refined + best_d_y * sin_t
    y_final = y_after_x - best_d_y * cos_t

    # Quality: depth of x-min and y-min relative to local mean
    depth_x = intens_x.min() / intens_x.mean() if intens_x.mean() > 0 else 1.0
    depth_y = intens_y.min() / intens_y.mean() if intens_y.mean() > 0 else 1.0
    # Edge fraction: how close to the window edge the best offset is
    edge_x = abs(min_idx_x - len(offsets) // 2) / (len(offsets) // 2)
    edge_y = abs(min_idx_y - len(offsets) // 2) / (len(offsets) // 2)

    quality = 1.0
    if depth_x > MIN_DEPTH_RATIO or depth_y > MIN_DEPTH_RATIO:
        quality = 0.0  # no clear scribe
    if edge_x > MAX_EDGE_FRAC or edge_y > MAX_EDGE_FRAC:
        quality = 0.0  # min at search-window edge (probably another scribe)
    # Refined depth ratio: lower = darker = better
    quality *= max(0.0, 1.0 - depth_x) * max(0.0, 1.0 - depth_y)

    return x_final, y_final, quality, depth_x, depth_y


def main() -> int:
    rgb = np.asarray(Image.open(PHOTO_PATH).convert("RGB"), dtype=np.float32)
    gray = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1]
            + 0.114 * rgb[..., 2]).astype(np.float32)
    theta_init = np.radians(INIT_THETA_DEG)
    H, W = gray.shape

    # Generate all (cl, rl) candidates inside the image
    anchors = []
    rejected = []
    for cl in range(0, 12):
        for rl in range(0, 7):
            x_pred, y_pred = grid_xy(cl, rl, theta_init, INIT_X0, INIT_Y0,
                                      INIT_D_COL, INIT_D_ROW)
            # Skip if predicted intersection is outside image (with margin)
            if not (50 < x_pred < W - 50 and 50 < y_pred < H - 50):
                rejected.append((cl, rl, "off-image"))
                continue
            x_r, y_r, q, dx_q, dy_q = refine_with_quality(
                gray, x_pred, y_pred, theta_init)
            if q < 0.005:
                rejected.append((cl, rl, f"q={q:.3f} d=({dx_q:.3f},{dy_q:.3f})"))
                continue
            anchors.append((cl, rl, x_r, y_r, q))

    print(f"Kept {len(anchors)}/{12*7} intersections after CV refinement + quality filter")
    print(f"Rejected: {len(rejected)} (reasons: off-image, low quality, or edge-of-window)")
    if rejected:
        for (cl, rl, reason) in rejected[:20]:
            print(f"  ({cl}, {rl}): {reason}")

    # Refit
    p0 = np.concatenate(([theta_init, INIT_X0, INIT_Y0], INIT_D_COL, INIT_D_ROW))
    sol = least_squares(_residuals, p0, args=(anchors,), method="lm")
    p = sol.x
    theta = p[0]
    x0, y0 = p[1], p[2]
    d_col = p[3:7]
    d_row = p[7:11]
    rmse = float(np.sqrt((sol.fun ** 2).mean()))

    print(f"\nRefit RMSE: {rmse:.2f} px over {len(anchors)} anchors")
    print(f"Rotation: {np.degrees(theta):.3f}° CW (was {INIT_THETA_DEG:.3f}°)")
    print(f"Grid origin: ({x0:.1f}, {y0:.1f})")
    print(f"\nDie widths by (col mod 4):")
    for k in range(4):
        flag = " ← WIDE" if d_col[k] == d_col.max() else ""
        print(f"  type {k}: {d_col[k]:7.2f} px{flag}")
    print(f"  super-cell width (4 dies): {d_col.sum():.2f}")
    print(f"Die heights by (row mod 4):")
    for k in range(4):
        flag = " ← TALL" if d_row[k] == d_row.max() else ""
        print(f"  type {k}: {d_row[k]:7.2f} px{flag}")
    print(f"  super-cell height (4 dies): {d_row.sum():.2f}")

    # Per-anchor residuals — show top 10 worst
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    res_list = []
    for (cl, rl, x_obs, y_obs, q) in anchors:
        u = _cum(d_col, cl)
        v = _cum(d_row, rl)
        x_pred = x0 + cos_t * u + sin_t * v
        y_pred = y0 + sin_t * u - cos_t * v
        res_list.append((cl, rl, x_pred - x_obs, y_pred - y_obs,
                         np.hypot(x_pred - x_obs, y_pred - y_obs), q))
    res_list.sort(key=lambda r: -r[4])
    print(f"\nTop 10 worst residuals:")
    for (cl, rl, dx, dy, r, q) in res_list[:10]:
        print(f"  ({cl:2d}, {rl}): dx={dx:+6.2f} dy={dy:+6.2f}  |r|={r:5.2f}  q={q:.3f}")

    # Save overlay
    fig, ax = plt.subplots(figsize=(20, 14))
    ax.imshow(rgb.astype(np.uint8))

    def gxy(cl, rl):
        return grid_xy(cl, rl, theta, x0, y0, d_col, d_row)

    for cl in range(0, 12):
        xs, ys = zip(*[gxy(cl, rl) for rl in range(0, 7)])
        is_wide = (cl % 4 == int(np.argmax(d_col)))
        ax.plot(xs, ys, color="magenta" if is_wide else "cyan",
                lw=0.9, alpha=0.85)
        x_lbl, y_lbl = gxy(cl, 0)
        ax.text(x_lbl, y_lbl + 30, f"c{cl}",
                color="magenta" if is_wide else "cyan", fontsize=10,
                ha="center", va="top",
                bbox=dict(boxstyle="round,pad=0.15", fc="black",
                          ec="none", alpha=0.5))
    for rl in range(0, 7):
        xs, ys = zip(*[gxy(cl, rl) for cl in range(0, 12)])
        is_tall = (rl % 4 == int(np.argmax(d_row)))
        ax.plot(xs, ys, color="red" if is_tall else "orange",
                lw=0.9, alpha=0.85)
        x_lbl, y_lbl = gxy(0, rl)
        label = f"r{rl}"
        if 1 <= rl <= 5:
            label += f" ({'ABCDEF'[rl-1]}/{'ABCDEF'[rl]})"
        ax.text(x_lbl - 30, y_lbl, label,
                color="red" if is_tall else "orange", fontsize=10,
                ha="right", va="center",
                bbox=dict(boxstyle="round,pad=0.15", fc="black",
                          ec="none", alpha=0.5))
    # Plot kept anchors (size = quality)
    for (cl, rl, x, y, q) in anchors:
        ax.plot(x, y, "o", color="lime", markersize=4 + 8 * q,
                markeredgewidth=0.8, markerfacecolor="none", alpha=0.7)
    # Die labels in centre
    for col in range(0, 11):
        for row_idx, row_letter in enumerate("ABCDEF"):
            xc, yc = gxy(col + 0.5, row_idx + 0.5)
            if 0 < xc < W and 0 < yc < H:
                ax.text(xc, yc, f"{col}{row_letter}", color="yellow",
                        fontsize=7, ha="center", va="center", alpha=0.7)
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.set_title(
        f"Dense-anchor super-cell fit ({len(anchors)} anchors)  |  "
        f"θ={np.degrees(theta):.3f}° CW  |  "
        f"d_col=[{d_col[0]:.0f},{d_col[1]:.0f},{d_col[2]:.0f},{d_col[3]:.0f}]  "
        f"d_row=[{d_row[0]:.0f},{d_row[1]:.0f},{d_row[2]:.0f},{d_row[3]:.0f}]  "
        f"RMSE={rmse:.2f}px"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "grid_supercell_dense.png"
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
