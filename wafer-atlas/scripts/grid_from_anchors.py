"""Solve the die grid affine from user-supplied scribe-intersection anchors.

Each anchor is (col_line, row_line, x_image, y_image) where:
  col_line = integer column-scribe index (col 0/1 → col_line 1)
  row_line = integer row-scribe index (row A=0, B=1, ..., F=5;
             between A and B → row_line 1)
  x_image, y_image = GIMP/image pixel coords (origin top-left, +y down)

The grid is an affine map (col_line, row_line) → (x, y):
    x = x0 + col_line * pcx + row_line * prx
    y = y0 + col_line * pcy + row_line * pry
With 3 anchors we have 6 equations in 6 unknowns — exact solution.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


PHOTO_PATH = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-13/"
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S/f_8/step_0131_c.jpg"
)
OUT_DIR = Path(__file__).parent.parent / "out"

# (col_line, row_line, x, y) — three user-supplied anchors.
# col 0/1 row A/B → col_line=1, row_line=1
# col 9/10 row A/B → col_line=10, row_line=1
# col 9/10 row E/F → col_line=10, row_line=5
ANCHORS = [
    (1, 1, 1636, 3624),
    (10, 1, 5890, 3972),
    (10, 5, 6050, 2076),
]

# Visible grid extent for overlay.
COL_LINES = range(0, 12)   # col 0 left edge through col 10 right edge → lines 0..11
ROW_LINES = range(0, 7)    # row A bottom through row F top → lines 0..6


def solve_grid(anchors):
    """Return (x0, y0, pcx, pcy, prx, pry) from anchors via least squares.

    Each anchor adds 2 equations (one for x, one for y), so 3 anchors → 6 eqs.
    With 6 unknowns this is exactly determined.
    """
    A = []
    b = []
    for (c, r, x, y) in anchors:
        A.append([1, 0, c, 0, r, 0])  # x equation: x = x0 + c*pcx + r*prx
        b.append(x)
        A.append([0, 1, 0, c, 0, r])  # y equation: y = y0 + c*pcy + r*pry
        b.append(y)
    A = np.array(A, dtype=np.float64)
    b = np.array(b, dtype=np.float64)
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    return sol


def grid_to_image(col_line, row_line, params):
    x0, y0, pcx, pcy, prx, pry = params
    return (x0 + col_line * pcx + row_line * prx,
            y0 + col_line * pcy + row_line * pry)


def main() -> int:
    params = solve_grid(ANCHORS)
    x0, y0, pcx, pcy, prx, pry = params
    print("Grid affine solution (col_line, row_line) → (x, y):")
    print(f"  origin (col=0, row=0): ({x0:.2f}, {y0:.2f})")
    print(f"  col step (per col_line):  dx = {pcx:+.3f}  dy = {pcy:+.3f}"
          f"  |step| = {np.hypot(pcx, pcy):.2f} px")
    print(f"  row step (per row_line):  dx = {prx:+.3f}  dy = {pry:+.3f}"
          f"  |step| = {np.hypot(prx, pry):.2f} px")
    rot_col = np.degrees(np.arctan2(pcy, pcx))
    rot_row = np.degrees(np.arctan2(prx, -pry))  # row points "up" in image (-y)
    print(f"  col axis tilt from image +x: {rot_col:+.3f}°"
          f"  (positive = clockwise rotation of the wafer)")
    print(f"  row axis tilt from image -y: {rot_row:+.3f}°"
          f"  (should match col axis tilt; gap = non-orthogonality)")
    # Non-orthogonality: angle between col and row vectors
    col_v = np.array([pcx, pcy])
    row_v = np.array([prx, pry])
    cos_angle = np.dot(col_v, row_v) / (np.linalg.norm(col_v) * np.linalg.norm(row_v))
    ang = np.degrees(np.arccos(np.clip(cos_angle, -1, 1)))
    print(f"  col vs row angle: {ang:.3f}° (90° = exactly orthogonal)")
    print()

    # Verify each anchor reproduces exactly
    print("Anchor verification:")
    for (c, r, x_in, y_in) in ANCHORS:
        x_pred, y_pred = grid_to_image(c, r, params)
        print(f"  (col_line={c}, row_line={r}): "
              f"given ({x_in}, {y_in}), predicted ({x_pred:.1f}, {y_pred:.1f}),"
              f"  residual ({x_pred - x_in:+.2f}, {y_pred - y_in:+.2f})")
    print()

    # Build full grid line endpoints for overlay
    rgb = np.asarray(Image.open(PHOTO_PATH).convert("RGB"))
    H, W = rgb.shape[:2]

    fig, ax = plt.subplots(figsize=(20, 14))
    ax.imshow(rgb)

    # Draw vertical scribes (constant col_line, varying row_line)
    for cl in COL_LINES:
        x_start, y_start = grid_to_image(cl, ROW_LINES.start - 0.5, params)
        x_end, y_end = grid_to_image(cl, ROW_LINES.stop - 0.5, params)
        ax.plot([x_start, x_end], [y_start, y_end], color="cyan", lw=0.8, alpha=0.8)
        # Label at the row_line=0.5 position (in the middle of row A area)
        # Actually label at the bottom of the visible grid.
        lx, ly = grid_to_image(cl, ROW_LINES.start, params)
        ax.text(lx, ly + 30, f"c{cl}", color="cyan", fontsize=10,
                ha="center", va="top",
                bbox=dict(boxstyle="round,pad=0.15", fc="black", ec="none", alpha=0.5))

    # Draw horizontal scribes (constant row_line, varying col_line)
    for rl in ROW_LINES:
        x_start, y_start = grid_to_image(COL_LINES.start - 0.5, rl, params)
        x_end, y_end = grid_to_image(COL_LINES.stop - 0.5, rl, params)
        ax.plot([x_start, x_end], [y_start, y_end], color="orange", lw=0.8, alpha=0.8)
        # Label at left side
        lx, ly = grid_to_image(COL_LINES.start, rl, params)
        # row_line k = between row letter k-1 and row letter k (A=0, B=1, ..., F=5)
        if rl == 0:
            label = f"r{rl} (below A)"
        elif rl <= 5:
            letter_pair = "ABCDEF"[rl - 1] + "/" + "ABCDEF"[rl] if rl < 6 else "ABCDEF"[rl - 1]
            label = f"r{rl} ({letter_pair})"
        else:
            label = f"r{rl} (above F)"
        ax.text(lx - 30, ly, label, color="orange", fontsize=10,
                ha="right", va="center",
                bbox=dict(boxstyle="round,pad=0.15", fc="black", ec="none", alpha=0.5))

    # Mark anchors
    for (c, r, x, y) in ANCHORS:
        ax.plot(x, y, "x", color="red", markersize=14, markeredgewidth=2)
        ax.annotate(f"({c},{r})", (x, y), color="red", fontsize=11,
                    xytext=(8, -8), textcoords="offset points",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="red", alpha=0.85))

    # Add die-label text in centre of each visible die
    for col in range(0, 11):
        for row_idx, row_letter in enumerate("ABCDEF"):
            # die (col, row) centre = grid (col_line=col+0.5, row_line=row_idx+0.5)
            x_c, y_c = grid_to_image(col + 0.5, row_idx + 0.5, params)
            if 0 < x_c < W and 0 < y_c < H:
                ax.text(x_c, y_c, f"{col}{row_letter}", color="yellow",
                        fontsize=8, ha="center", va="center", alpha=0.75)

    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.set_title(
        f"Die-grid overlay from 3 user anchors  |  "
        f"col pitch={np.hypot(pcx, pcy):.1f}px  row pitch={np.hypot(prx, pry):.1f}px  "
        f"rotation={rot_col:+.2f}° CW"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "grid_from_anchors.png"
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    print(f"Saved overlay: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
