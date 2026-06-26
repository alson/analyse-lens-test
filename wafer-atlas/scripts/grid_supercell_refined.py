"""Refine user anchors by CV snap-to-scribe, then refit super-cell grid.

Each anchor is a scribe-intersection where a vertical scribe (running at
the wafer's +y direction, ~90° tilted by theta) crosses a horizontal
scribe (running at the wafer's +x direction). To refine:

  1. For each candidate x_offset in [-r, +r], sample a strip of length
     2*L+1 along the predicted *vertical scribe* direction passing
     through (x_init + dx, y_init). Mean of those samples is the
     intensity if the vertical scribe were at x_init + dx. The actual
     scribe is the dark valley → argmin over dx.

  2. Same for y_offset against the horizontal scribe direction.

  3. Refined anchor = (x_init + best_dx, y_init + best_dy).

After refinement re-run the super-cell fit. Saves a new overlay PNG.
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

ANCHORS = [
    (1, 1, 1636, 3624),
    (10, 1, 5890, 3972),
    (10, 5, 6050, 2076),
    (3, 1, 2544, 3694),
    (3, 2, 2595, 3152),
    (3, 3, 2630, 2699),
    (3, 4, 2675, 2253),
    (3, 5, 2704, 1803),
    (2, 2, 2134, 3116),
    (4, 2, 3043, 3193),
    (5, 2, 3585, 3236),
    (6, 2, 4039, 3269),
    (7, 2, 4487, 3307),
    (8, 2, 4935, 3344),
    (9, 2, 5476, 3391),
    (10, 2, 5936, 3424),
]

# Initial estimate (from grid_supercell.py output)
THETA0_DEG = 4.70
SEARCH_RADIUS = 25       # px to search either side of the user-given anchor
STRIP_HALF_LENGTH = 80   # half-length of along-scribe strip we average over
SMOOTH_SIGMA = 0.0       # set >0 to smooth the strip; 0 = raw


def _cum(d4: np.ndarray, k: float) -> float:
    if k <= 0:
        return 0.0
    k_int = int(np.floor(k))
    frac = k - k_int
    full_cycles = k_int // 4
    remainder = k_int % 4
    cum_int = full_cycles * d4.sum() + d4[:remainder].sum()
    if frac > 0:
        cum_int += frac * d4[remainder]
    return cum_int


def _residuals(params: np.ndarray, anchors: list) -> np.ndarray:
    theta, x0, y0 = params[0], params[1], params[2]
    d_col = params[3:7]
    d_row = params[7:11]
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


def _sample_strip(image: np.ndarray, x_centre: float, y_centre: float,
                  direction: tuple[float, float],
                  half_length: int = STRIP_HALF_LENGTH) -> float:
    """Mean image intensity along a line through (x_centre, y_centre).

    Direction is a unit vector in image space. Samples 2*half_length+1
    points centred on the input.
    """
    s = np.arange(-half_length, half_length + 1, dtype=np.float64)
    dx, dy = direction
    xs = x_centre + s * dx
    ys = y_centre + s * dy
    H, W = image.shape
    xs_int = np.clip(np.round(xs).astype(int), 0, W - 1)
    ys_int = np.clip(np.round(ys).astype(int), 0, H - 1)
    return float(image[ys_int, xs_int].mean())


def refine_anchor(image: np.ndarray, x_init: float, y_init: float,
                  theta_rad: float,
                  search_radius: int = SEARCH_RADIUS,
                  strip_half_length: int = STRIP_HALF_LENGTH
                  ) -> tuple[float, float, np.ndarray, np.ndarray]:
    """Find the local scribe-cross by independent x/y line searches."""
    cos_t = np.cos(theta_rad)
    sin_t = np.sin(theta_rad)
    # Vertical scribe direction in image: (sin_t, -cos_t)  (wafer +y tilted CW)
    v_dir = (sin_t, -cos_t)
    # Horizontal scribe direction in image: (cos_t, sin_t)  (wafer +x tilted CW)
    h_dir = (cos_t, sin_t)
    # The cross-search direction is perpendicular to each scribe.
    # x search: move along (cos_t, sin_t) but we want to move perpendicular
    # to vertical scribe, which is (cos_t, sin_t) — i.e. the horizontal scribe
    # direction. Step in that direction by delta.
    offsets = np.arange(-search_radius, search_radius + 1)
    intens_x = []
    for d in offsets:
        cx = x_init + d * cos_t
        cy = y_init + d * sin_t
        intens_x.append(_sample_strip(image, cx, cy, v_dir, strip_half_length))
    intens_x = np.array(intens_x)
    best_d_x = offsets[int(np.argmin(intens_x))]
    x_refined = x_init + best_d_x * cos_t
    y_after_x = y_init + best_d_x * sin_t

    intens_y = []
    for d in offsets:
        cx = x_refined + d * sin_t
        cy = y_after_x - d * cos_t
        # we want to step perpendicular to horizontal scribe, i.e. along
        # vertical scribe direction (sin_t, -cos_t)
        intens_y.append(_sample_strip(image, cx, cy, h_dir, strip_half_length))
    intens_y = np.array(intens_y)
    best_d_y = offsets[int(np.argmin(intens_y))]
    x_final = x_refined + best_d_y * sin_t
    y_final = y_after_x - best_d_y * cos_t
    return x_final, y_final, intens_x, intens_y


def main() -> int:
    rgb = np.asarray(Image.open(PHOTO_PATH).convert("RGB"), dtype=np.float32)
    gray = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1]
            + 0.114 * rgb[..., 2]).astype(np.float32)
    theta_init = np.radians(THETA0_DEG)

    refined = []
    print(f"{'(cl,rl)':>8} {'(x_old, y_old)':>20} → {'(x_new, y_new)':>20}"
          f" {'shift':>14}")
    for (cl, rl, x, y) in ANCHORS:
        x_r, y_r, _, _ = refine_anchor(gray, x, y, theta_init)
        dx, dy = x_r - x, y_r - y
        refined.append((cl, rl, x_r, y_r))
        print(f"  ({cl:2d}, {rl:1d})  ({x:6.1f}, {y:6.1f})"
              f"  →  ({x_r:6.1f}, {y_r:6.1f})  "
              f"({dx:+5.1f}, {dy:+5.1f})")

    # Refit
    d_col0 = np.array([542.0, 458.0, 456.0, 448.0])
    d_row0 = np.array([452.0, 546.0, 455.0, 448.0])
    cos_t0 = np.cos(theta_init)
    sin_t0 = np.sin(theta_init)
    x0_init = refined[0][2] - cos_t0 * d_col0[0] - sin_t0 * d_row0[0]
    y0_init = refined[0][3] - sin_t0 * d_col0[0] + cos_t0 * d_row0[0]
    p0 = np.concatenate(([theta_init, x0_init, y0_init], d_col0, d_row0))
    sol = least_squares(_residuals, p0, args=(refined,), method="lm")
    p = sol.x
    theta = p[0]
    x0, y0 = p[1], p[2]
    d_col = p[3:7]
    d_row = p[7:11]
    rmse = float(np.sqrt((sol.fun ** 2).mean()))

    print(f"\nRefit RMSE: {rmse:.2f} px over {len(refined)} refined anchors")
    print(f"Rotation: {np.degrees(theta):.3f}° CW")
    print(f"Grid origin (0, 0): ({x0:.1f}, {y0:.1f})")
    print(f"\nDie widths by (col mod 4):")
    for k in range(4):
        flag = "  ← WIDE" if d_col[k] == d_col.max() else ""
        print(f"  type {k}: {d_col[k]:6.2f} px{flag}")
    print(f"  super-cell width (4 dies): {d_col.sum():.2f} px")
    print(f"Die heights by (row mod 4):")
    for k in range(4):
        flag = "  ← TALL" if d_row[k] == d_row.max() else ""
        print(f"  type {k}: {d_row[k]:6.2f} px{flag}")
    print(f"  super-cell height (4 dies): {d_row.sum():.2f} px")

    # Per-anchor refit residuals
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    print(f"\nResiduals on refined anchors:")
    for (cl, rl, x_obs, y_obs) in refined:
        u = _cum(d_col, cl)
        v = _cum(d_row, rl)
        x_pred = x0 + cos_t * u + sin_t * v
        y_pred = y0 + sin_t * u - cos_t * v
        print(f"  ({cl:2d}, {rl:1d})  pred ({x_pred:7.1f}, {y_pred:7.1f})"
              f"  obs ({x_obs:7.1f}, {y_obs:7.1f})"
              f"  resid ({x_pred - x_obs:+6.2f}, {y_pred - y_obs:+6.2f})")

    # Overlay
    H, W = gray.shape

    def grid_xy(cl, rl):
        u = _cum(d_col, cl) if cl >= 0 else -_cum(d_col, -cl)
        v = _cum(d_row, rl) if rl >= 0 else -_cum(d_row, -rl)
        return (x0 + cos_t * u + sin_t * v,
                y0 + sin_t * u - cos_t * v)

    fig, ax = plt.subplots(figsize=(20, 14))
    ax.imshow(rgb.astype(np.uint8))
    for cl in range(0, 12):
        xs, ys = zip(*[grid_xy(cl, rl) for rl in range(0, 7)])
        col_type = cl % 4
        is_wide = (col_type == int(np.argmax(d_col)))
        color = "magenta" if is_wide else "cyan"
        ax.plot(xs, ys, color=color, lw=0.9, alpha=0.85)
        x_lbl, y_lbl = grid_xy(cl, 0)
        ax.text(x_lbl, y_lbl + 30, f"c{cl}", color=color, fontsize=10,
                ha="center", va="top",
                bbox=dict(boxstyle="round,pad=0.15", fc="black",
                          ec="none", alpha=0.5))
    for rl in range(0, 7):
        xs, ys = zip(*[grid_xy(cl, rl) for cl in range(0, 12)])
        row_type = rl % 4
        is_tall = (row_type == int(np.argmax(d_row)))
        color = "red" if is_tall else "orange"
        ax.plot(xs, ys, color=color, lw=0.9, alpha=0.85)
        x_lbl, y_lbl = grid_xy(0, rl)
        if 1 <= rl <= 5:
            letter_pair = "ABCDEF"[rl - 1] + "/" + "ABCDEF"[rl]
            label = f"r{rl} ({letter_pair})"
        elif rl == 0:
            label = "r0 (below A)"
        else:
            label = "r6 (above F)"
        ax.text(x_lbl - 30, y_lbl, label, color=color, fontsize=10,
                ha="right", va="center",
                bbox=dict(boxstyle="round,pad=0.15", fc="black",
                          ec="none", alpha=0.5))
    # Plot both original and refined anchors
    for (cl, rl, x_o, y_o), (_, _, x_r, y_r) in zip(ANCHORS, refined):
        ax.plot([x_o, x_r], [y_o, y_r], "-", color="white",
                lw=0.6, alpha=0.5)
        ax.plot(x_o, y_o, ".", color="white", markersize=4, alpha=0.7)
        ax.plot(x_r, y_r, "x", color="lime", markersize=12, markeredgewidth=1.8)
        ax.annotate(f"({cl},{rl})", (x_r, y_r), color="lime", fontsize=9,
                    xytext=(6, -6), textcoords="offset points",
                    bbox=dict(boxstyle="round,pad=0.12", fc="black",
                              ec="lime", alpha=0.6))
    # Die labels
    for col in range(0, 11):
        for row_idx, row_letter in enumerate("ABCDEF"):
            xc, yc = grid_xy(col + 0.5, row_idx + 0.5)
            if 0 < xc < W and 0 < yc < H:
                ct = col % 4
                rt = row_idx % 4
                if ct == int(np.argmax(d_col)) and rt == int(np.argmax(d_row)):
                    s, c = f"{col}{row_letter}*", "yellow"
                elif ct == int(np.argmax(d_col)):
                    s, c = f"{col}{row_letter}↔", "magenta"
                elif rt == int(np.argmax(d_row)):
                    s, c = f"{col}{row_letter}↕", "red"
                else:
                    s, c = f"{col}{row_letter}", "yellow"
                ax.text(xc, yc, s, color=c, fontsize=8, ha="center",
                        va="center", alpha=0.85)
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.set_title(
        f"CV-refined super-cell  |  θ={np.degrees(theta):.2f}° CW  |  "
        f"d_col=[{d_col[0]:.0f},{d_col[1]:.0f},{d_col[2]:.0f},{d_col[3]:.0f}]  "
        f"d_row=[{d_row[0]:.0f},{d_row[1]:.0f},{d_row[2]:.0f},{d_row[3]:.0f}]  "
        f"RMSE={rmse:.1f}px  white→lime: anchor shift"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "grid_supercell_refined.png"
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
