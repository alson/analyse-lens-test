"""Probe: try the (2,1) 2B "horizontal lines + serpent" feature as a SLANTED EDGE
(task item 5 — the user-flagged `use_for_slanted_edge` candidate, never tried).

The atlas marks (2,1) both use_for_fft AND use_for_slanted_edge ("may have long
parallel edges"). We register a sharp sweep, locate the (2,1) experimental block,
and lay short Segments ACROSS individual horizontal lines near the block centre, then
run methods.slanted_edge.mtf50_erf (super-resolved, ceiling-validated). The question:
do the long parallel edges give a clean step ≤ the diffraction ceiling, or does the
grating periodicity break the single-step ESF model?
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from tile_sharpness.methods.slanted_edge import Segment, mtf50_erf, mtf50_iso
from tile_sharpness import optics

WA = Path("/home/alson/shared/projects/personal/fotografie/analyse-lens-test/wafer-atlas/scripts")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


reg_auto = _load("reg_auto", WA / "reg_auto.py")
af = _load("anchor_fit_sweep", WA / "anchor_fit_sweep.py")
ATLAS = json.load(open(WA.parent / "atlas.json"))
M_ANCHOR_SCALE = 1.6549
LPMM_PER_CYPX = 1000.0 / 4.35


def die_uv_to_img(col, row, u, v, p):
    if "k1" in p:
        return reg_auto.grid_xy_distorted(col + u, row + v, p)
    return af.grid_xy(col + u, row + v, p, ATLAS)


def main():
    sweep = Path(sys.argv[1])
    n_marked = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
    jpgs = sorted(sweep.glob("*.jpg"))
    # register on a central-sharp frame (reuse atlas_periodic_fft.register)
    A = _load("atlas_periodic_fft", Path(__file__).resolve().parent / "atlas_periodic_fft.py")
    p = A.register(jpgs)
    if p is None:
        print("reg FAILED"); return
    M = p["scale"] / M_ANCHOR_SCALE
    n_eff = optics.effective_fnumber(n_marked, M)
    ceil_cypx = optics.diffraction_mtf50_sensor_lpmm(n_eff) / LPMM_PER_CYPX
    print(f"M={M:.3f} N_eff={n_eff:.1f} ceiling MTF50={ceil_cypx:.3f} cy/px")
    # find an in-FOV (2,1) experimental block
    found = None
    for col in range(11):
        for row in range(6):
            if f"({col % 4}, {row % 4})" != "(2, 1)":
                continue
            dt = ATLAS["die_types"]["(2, 1)"]
            exp = dt["feature_inventory"]["experimental"]
            if not exp:
                continue
            u0, v0, u1, v1 = exp[0]["bbox_uv"]
            cs = [die_uv_to_img(col, row, u, v, p) for u, v in
                  [(u0, v0), (u0, v1), (u1, v0), (u1, v1)]]
            xs = [c[0] for c in cs]; ys = [c[1] for c in cs]
            cx, cy = sum(xs) / 4, sum(ys) / 4
            if 300 < cx < 7956 and 300 < cy < 5204:        # block centre well in-frame
                found = (col, row, max(80, min(xs)), max(80, min(ys)),
                         min(8176, max(xs)), min(5424, max(ys))); break
        if found:
            break
    if not found:
        print("no in-FOV (2,1) experimental block"); return
    col, row, x0, y0, x1, y1 = found
    print(f"(2,1) block at die {col}{'ABCDEF'[row]}: img bbox ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})")
    # sharpest frame by block lapvar
    bf, bidx = -1, None
    for k, jp in enumerate(jpgs):
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        roi = g[int(y0):int(y1), int(x0):int(x1)]
        lv = cv2.Laplacian(roi.astype(np.float32), cv2.CV_32F).var()
        if lv > bf:
            bf, bidx, gbest = lv, k, g
    print(f"sharpest block frame: shot {bidx} lapvar={bf:.0f}")
    # lay vertical segments (crossing horizontal lines) at several u positions
    cx = 0.5 * (x0 + x1)
    results = []
    for frac in (0.3, 0.5, 0.7):
        sx = x0 + frac * (x1 - x0)
        # a short vertical segment ~60px tall crossing a few lines
        seg = Segment(x0=float(sx), y0=float(0.5 * (y0 + y1) - 35),
                      x1=float(sx + 6.0), y1=float(0.5 * (y0 + y1) + 35))  # slight slant
        m_erf = mtf50_erf(gbest.astype(np.float32), seg, half_window_px=20.0, combine="min")
        m_iso = mtf50_iso(gbest.astype(np.float32), seg, half_window_px=20.0, combine="min")
        results.append((frac, m_erf, m_iso))
    print(f"\n{'u_frac':<8}{'erf_cypx':>10}{'iso_cypx':>10}{'vs ceiling':>14}")
    for frac, me, mi in results:
        s = ""
        if me:
            s = "OVER" if me > ceil_cypx + 0.02 else "<=ceil"
        print(f"{frac:<8}{(me or float('nan')):10.3f}{(mi or float('nan')):10.3f}{s:>14}")
    print("\nNOTE: a vertical segment across a horizontal-LINE GRATING crosses MANY "
          "edges; mtf50_erf fits a single step, so multiple lines in-window break the "
          "ESF model. This feature is a grating (FFT target), not an isolated SE step.")


if __name__ == "__main__":
    main()
