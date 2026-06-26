"""Fit a 4-row × 4-col super-cell grid with per-type pitches.

Model:
    Per-die widths d_col[k mod 4] for k in 0..3.
    Per-die heights d_row[k mod 4] for k in 0..3.
    Wafer rotation theta (CW positive in image coords).
    Grid origin (x0, y0) = image position of (col_line=0, row_line=0).

For grid point (cl, rl):
    u(cl) = sum_{j=0}^{cl-1} d_col[j mod 4]   (cumulative wafer-frame x)
    v(rl) = sum_{j=0}^{rl-1} d_row[j mod 4]   (cumulative wafer-frame y)
    x_image = x0 + cos(theta) * u(cl) + sin(theta) * v(rl)
    y_image = y0 + sin(theta) * u(cl) - cos(theta) * v(rl)

Unknowns: theta, x0, y0, d_col[0..3], d_row[0..3] = 11 parameters.
Anchors: 16 (3 original + 5 along c3 + 8 along r2 (skipping c1 typo))
       → 32 equations. Over-determined.

Wide-type assignment:
    col mod 4 = 0 → wide (cols 0, 4, 8): WIDE_COL_TYPE = 0
    row mod 4 = 1 → tall (rows B, F): TALL_ROW_TYPE = 1
This is implicit in the data and recovered from the LS fit.
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

# All user-supplied anchors: (col_line, row_line, x_image, y_image).
ANCHORS = [
    # Original 3
    (1, 1, 1636, 3624),
    (10, 1, 5890, 3972),
    (10, 5, 6050, 2076),
    # Along c3 (varying row_line)
    (3, 1, 2544, 3694),
    (3, 2, 2595, 3152),
    (3, 3, 2630, 2699),
    (3, 4, 2675, 2253),
    (3, 5, 2704, 1803),
    # Along r2 (varying col_line; skipping c1 = (1683, 3802) — y looks like
    # a transposed-digit typo of 3082; ignored to keep clean numbers)
    (2, 2, 2134, 3116),
    # c3, r2 already above
    (4, 2, 3043, 3193),
    (5, 2, 3585, 3236),
    (6, 2, 4039, 3269),
    (7, 2, 4487, 3307),
    (8, 2, 4935, 3344),
    (9, 2, 5476, 3391),
    (10, 2, 5936, 3424),
]


def _cum(d4: np.ndarray, k: float) -> float:
    """Cumulative sum of d4[j mod 4] for j in 0..k-1; handles fractional k.

    For non-integer k, returns _cum(int(k)) + (k - int(k)) * d4[int(k) mod 4],
    which linearly interpolates the cumulative position inside die int(k).
    """
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


def main() -> int:
    # Initial guesses
    theta0 = np.radians(4.68)
    d_col0 = np.array([542.0, 455.0, 455.0, 448.0])  # type 0 wide
    d_row0 = np.array([450.0, 542.0, 453.0, 446.0])  # type 1 tall
    # Origin: x0, y0 is (col_line=0, row_line=0). From original P1
    # at (1, 1): x0 ≈ 1636 - cos*d_col[0] - sin*d_row[0], y0 ≈ 3624 - sin*d_col[0] + cos*d_row[0]
    cos_t = np.cos(theta0)
    sin_t = np.sin(theta0)
    x0_init = 1636 - cos_t * d_col0[0] - sin_t * d_row0[0]
    y0_init = 3624 - sin_t * d_col0[0] + cos_t * d_row0[0]
    p0 = np.concatenate(([theta0, x0_init, y0_init], d_col0, d_row0))

    sol = least_squares(_residuals, p0, args=(ANCHORS,), method="lm")
    p = sol.x
    theta = p[0]
    x0, y0 = p[1], p[2]
    d_col = p[3:7]
    d_row = p[7:11]
    rmse = float(np.sqrt((sol.fun ** 2).mean()))

    print(f"Fit converged in {sol.nfev} function evals.")
    print(f"RMSE residual: {rmse:.2f} px over {len(ANCHORS)} anchors\n")
    print(f"Rotation: {np.degrees(theta):.3f}° clockwise")
    print(f"Grid origin (col_line=0, row_line=0): ({x0:.1f}, {y0:.1f})")
    print(f"\nDie widths by (col mod 4):")
    for k in range(4):
        flag = "  ← WIDE" if d_col[k] == d_col.max() else ""
        print(f"  type {k} (cols {k}, {k+4}, {k+8}): {d_col[k]:6.2f} px{flag}")
    print(f"  super-cell width (4 dies): {d_col.sum():.2f} px"
          f"  mean die: {d_col.mean():.2f} px")
    print(f"\nDie heights by (row mod 4) [A=0, B=1, ..., F=5]:")
    for k in range(4):
        flag = "  ← TALL" if d_row[k] == d_row.max() else ""
        rows_in_type = ["A,E", "B,F", "C", "D"][k]
        print(f"  type {k} (rows {rows_in_type}): {d_row[k]:6.2f} px{flag}")
    print(f"  super-cell height (4 dies): {d_row.sum():.2f} px"
          f"  mean die: {d_row.mean():.2f} px")

    # Per-anchor residuals
    print("\nPer-anchor residuals (x_pred - x_obs, y_pred - y_obs):")
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    for (cl, rl, x_obs, y_obs) in ANCHORS:
        u = _cum(d_col, cl)
        v = _cum(d_row, rl)
        x_pred = x0 + cos_t * u + sin_t * v
        y_pred = y0 + sin_t * u - cos_t * v
        print(f"  ({cl:2d}, {rl:1d}) given ({x_obs}, {y_obs}) "
              f"pred ({x_pred:7.1f}, {y_pred:7.1f}) "
              f"resid ({x_pred - x_obs:+6.2f}, {y_pred - y_obs:+6.2f})")

    # Overlay
    rgb = np.asarray(Image.open(PHOTO_PATH).convert("RGB"))
    H, W = rgb.shape[:2]

    def grid_xy(cl, rl):
        u = _cum(d_col, cl) if cl >= 0 else -_cum(d_col, -cl)
        v = _cum(d_row, rl) if rl >= 0 else -_cum(d_row, -rl)
        return (x0 + cos_t * u + sin_t * v,
                y0 + sin_t * u - cos_t * v)

    fig, ax = plt.subplots(figsize=(20, 14))
    ax.imshow(rgb)
    for cl in range(0, 12):
        xs, ys = zip(*[grid_xy(cl, rl) for rl in range(0, 7)])
        # Wide cols in a different colour
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

    # Anchors
    for (cl, rl, x, y) in ANCHORS:
        ax.plot(x, y, "x", color="lime", markersize=12, markeredgewidth=1.8)
        ax.annotate(f"({cl},{rl})", (x, y), color="lime", fontsize=9,
                    xytext=(6, -6), textcoords="offset points",
                    bbox=dict(boxstyle="round,pad=0.12", fc="black",
                              ec="lime", alpha=0.6))

    # Die labels in centre
    for col in range(0, 11):
        for row_idx, row_letter in enumerate("ABCDEF"):
            xc, yc = grid_xy(col + 0.5, row_idx + 0.5)
            if 0 < xc < W and 0 < yc < H:
                # Mark super-cell type
                ct = col % 4
                rt = row_idx % 4
                if ct == int(np.argmax(d_col)) and rt == int(np.argmax(d_row)):
                    s = f"{col}{row_letter}*"  # wide & tall
                    c = "yellow"
                elif ct == int(np.argmax(d_col)):
                    s = f"{col}{row_letter}↔"
                    c = "magenta"
                elif rt == int(np.argmax(d_row)):
                    s = f"{col}{row_letter}↕"
                    c = "red"
                else:
                    s = f"{col}{row_letter}"
                    c = "yellow"
                ax.text(xc, yc, s, color=c, fontsize=8, ha="center",
                        va="center", alpha=0.85)

    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.set_title(
        f"Super-cell grid  |  θ={np.degrees(theta):.2f}° CW  |  "
        f"d_col=[{d_col[0]:.0f},{d_col[1]:.0f},{d_col[2]:.0f},{d_col[3]:.0f}] (type 0 wide)  |  "
        f"d_row=[{d_row[0]:.0f},{d_row[1]:.0f},{d_row[2]:.0f},{d_row[3]:.0f}] (type 1 tall)  |  "
        f"RMSE={rmse:.1f}px"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "grid_supercell.png"
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
