"""Prove the Sigma105+TC 2:1 ambiguity is MEASUREMENT-EQUIVALENT: candidate
labelings col_first in {2,6} (and row in {1,5}, though the 4D bar pins row=3)
are the SAME super-cell phase (2==6 mod 4, 1==5 mod 4). Fit the affine for each
and confirm: identical scale/M, identical residual, identical die-TYPE
assignment per detected scribe; ONLY x0/y0 differ, by an integer number of
super-cell pitches (4*sum(d_col) etc)."""
from __future__ import annotations
import importlib.util, glob
from pathlib import Path
import numpy as np, cv2

WA = Path(__file__).resolve().parent
def _load(n):
    s = importlib.util.spec_from_file_location(n, WA / f"{n}.py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
ra = _load("reg_auto"); af = ra.af; ATLAS = ra.ATLAS
D_COL, D_ROW = ra.D_COL, ra.D_ROW

PATH = ("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
        "Sigma Macro 105mm F2.8 EX DG OS HSM + TC-2001/2_1/F11/"
        "15287|Sigma Macro 105mm F2.8 EX DG OS HSM + TC-2001|2_1|210.0 mm|F11|"
        "alm-20260204-202935-2917.jpg")
SUPER_COL = 4 * sum(D_COL)   # super-cell pitch (full-res atlas px)
SUPER_ROW = 4 * sum(D_ROW)


def fit(det, cf, rf):
    col_x, row_y = det["col_x"], det["row_y"]
    cl = ra._labels(col_x, cf)
    rr = ra._rel_indices(row_y); rl_top = rf + int(rr[-1])
    rl = [rl_top - int(r) for r in rr]
    pairs = [(cl[ci], rl[ri], *ra.derot_to_orig(float(xd), float(yd), det))
             for ci, xd in enumerate(col_x) for ri, yd in enumerate(row_y)]
    pscale, _ = ra.pitch_implied_scale(det)
    p = af.fit_sweep_affine(pairs, ATLAS, theta_init_deg=det["tilt"],
                            scale_init=pscale if pscale else 0.5)
    return p, cl, rl


det = ra.detect(PATH)
print("col_x", np.round(det["col_x"],1).tolist(), "row_y", np.round(det["row_y"],1).tolist())
print(f"SUPER_COL pitch(full px)={SUPER_COL:.1f}  SUPER_ROW={SUPER_ROW:.1f}")
print(f"{'cf,rf':>8} {'scale':>9} {'M':>8} {'rmse':>8} {'x0':>10} {'y0':>10} {'theta_deg':>10}  col_types/row_types")
results = {}
for cf in (2, 6):
    for rf in (1, 5):
        p, cl, rl = fit(det, cf, rf)
        M = p["scale"]/ra.M_ANCHOR_SCALE
        ctypes = [c % 4 for c in cl]; rtypes = [r % 4 for r in rl]
        results[(cf,rf)] = p
        print(f"{cf},{rf:>5} {p['scale']:>9.4f} {M:>8.4f} {p['rmse_px']:>8.2f} "
              f"{p['x0_img']:>10.1f} {p['y0_img']:>10.1f} {p['theta_deg']:>10.4f}  "
              f"cl%4={ctypes} rl%4={rtypes}")

# show x0/y0 deltas vs (2,1) baseline, in units of super-cell pitch * scale
base = results[(2,1)]
print("\nOrigin shift vs (cf=2,rf=1), expressed in super-cell units:")
for k, p in results.items():
    dx = p["x0_img"] - base["x0_img"]; dy = p["y0_img"] - base["y0_img"]
    print(f"  {k}: dx={dx:.1f} dy={dy:.1f}  |  dx/(scale*SUPER_COL)={dx/(p['scale']*SUPER_COL):+.3f} "
          f"dy/(scale*SUPER_ROW)={dy/(p['scale']*SUPER_ROW):+.3f}")
