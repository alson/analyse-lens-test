"""Diagnose the Sigma105+TC-2001 2:1 honest-refusal, and compare to Sigma150+TC
(which registers). For the sharpest frame of each: dump detected scribes, robust
pitch / pitch-implied M, candidate col/row phases & offsets, edge_visibility,
4D-bar count, and the register() outcome. Then for EACH candidate (col,row)
labeling, list the die TYPES that fall in the FOV (the disambiguation signal).
"""
from __future__ import annotations
import importlib.util, glob
from pathlib import Path
import numpy as np, cv2

WA = Path(__file__).resolve().parent
def _load(n):
    s = importlib.util.spec_from_file_location(n, WA / f"{n}.py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
ra = _load("reg_auto")
af = ra.af
ATLAS = ra.ATLAS
D_COL, D_ROW = ra.D_COL, ra.D_ROW
N_COL_LINES, N_ROW_LINES = ra.N_COL_LINES, ra.N_ROW_LINES
IMG_W, IMG_H = 8256, 5504

TYPE_NAME = {(0,0):"E-pads",(0,1):"B-3x3grid",(0,2):"C-pads",(0,3):"D-4Dbar",
             (1,0):"E",(1,1):"B-resistors",(1,2):"C-3band",(1,3):"D",
             (2,0):"E-coarsepads",(2,1):"2B-SERPENT",(2,2):"C-cyanrect",(2,3):"D-1Blike",
             (3,0):"E-3band",(3,1):"3B-magrect",(3,2):"C-2padblk",(3,3):"D-pads"}

CFG = {
 "Sigma105+TC": "Sigma Macro 105mm F2.8 EX DG OS HSM + TC-2001/2_1/F11",
 "Sigma150+TC": "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001/2_1/F11",
}
RAW = "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29"


def reduced_lapvar(path):
    g = cv2.imread(str(path), cv2.IMREAD_REDUCED_GRAYSCALE_4)
    if g is None: return -1.0
    h, w = g.shape
    c = g[h//2-200:h//2+200, w//2-200:w//2+200]
    return float(cv2.Laplacian(c.astype(np.float32), cv2.CV_32F).var())


def fov_dies(p, min_cov=0.6):
    """Dies whose centre is in-frame, with coverage, for a fitted affine p."""
    out = []
    for col in range(N_COL_LINES - 1):
        for row in range(N_ROW_LINES - 1):
            cor = [ra.grid_xy_distorted(col+u, row+v, p) for u,v in
                   [(0,0),(0,1),(1,0),(1,1)]]
            xs=[c[0] for c in cor]; ys=[c[1] for c in cor]
            bx0,by0,bx1,by1=min(xs),min(ys),max(xs),max(ys)
            cx,cy=(bx0+bx1)/2,(by0+by1)/2
            if not (0<cx<IMG_W and 0<cy<IMG_H): continue
            ix0,iy0,ix1,iy1=max(0,bx0),max(0,by0),min(IMG_W,bx1),min(IMG_H,by1)
            cov=(ix1-ix0)*(iy1-iy0)/max(1,(bx1-bx0)*(by1-by0))
            if cov>=min_cov:
                out.append((col,row,(col%4,row%4),round(cov,2),int(cx),int(cy)))
    return out


def fit_for_offset(det, cf, rf):
    """Fit affine for a hypothesized (col_first, row_first) labeling."""
    col_x, row_y = det["col_x"], det["row_y"]
    cl = ra._labels(col_x, cf)
    row_rel = ra._rel_indices(row_y)
    rl_top = rf + int(row_rel[-1])
    rl = [rl_top - int(r) for r in row_rel]
    pairs = []
    for ci, xd in enumerate(col_x):
        for ri, yd in enumerate(row_y):
            xo, yo = ra.derot_to_orig(float(xd), float(yd), det)
            pairs.append((cl[ci], rl[ri], xo, yo))
    pscale, _ = ra.pitch_implied_scale(det)
    p = af.fit_sweep_affine(pairs, ATLAS, theta_init_deg=det["tilt"],
                            scale_init=pscale if pscale else 0.5)
    p["model"] = "similarity"
    return p


def run(name, sub):
    print(f"\n{'='*72}\n{name}  ({sub})")
    jpgs = sorted(glob.glob(f"{RAW}/{sub}/*.jpg"))
    print(f"  {len(jpgs)} frames")
    lv = sorted(((reduced_lapvar(j), j) for j in jpgs), reverse=True)
    path = lv[0][1]
    print(f"  sharpest: {Path(path).name}")
    det = ra.detect(path)
    print(f"  tilt={det['tilt']:+.3f} ds_scale={det['ds_scale']:.4f}")
    print(f"  col_x(derot ds-px)={np.round(det['col_x'],1).tolist()}")
    print(f"  row_y(derot ds-px)={np.round(det['row_y'],1).tolist()}")
    print(f"  col_unit={det.get('col_unit')} row_unit={det.get('row_unit')}")
    ps, pM = ra.pitch_implied_scale(det)
    print(f"  pitch_implied scale={ps} M={pM}")

    # phases / candidates (mirror register())
    col_rel = ra._rel_indices(det["col_x"]); n_col_runs = N_COL_LINES - int(col_rel[-1])
    row_pos_wafer = np.sort(-det["row_y"].astype(float))
    row_cands = ra.candidate_offsets(row_pos_wafer, D_ROW, ra.TALL_ROW, N_ROW_LINES)
    ev = ra.edge_visibility(det)
    bars = ra.detect_4d_bars(det)
    print(f"  edge_visibility={ {k:round(v,3) for k,v in ev.items()} }")
    print(f"  4D bars detected: {len(bars)} {[(int(b[0]),int(b[1])) for b in bars]}")
    print(f"  n_col_runs={n_col_runs} row_cands={row_cands}")

    r = ra.register(name, det, anchors=None)
    print(f"  REGISTER: success={r.get('success')} reason={r.get('reason')}")
    print(f"    col_cands={r.get('col_candidates')} col_method={r.get('col_method')} col_first={r.get('col_first')}")
    print(f"    row_cands={r.get('row_candidates')} row_method={r.get('row_method')} row_first={r.get('row_first')}")

    # Enumerate candidate labelings & their FOV die-types
    col_cands = r.get('col_candidates') or list(range(n_col_runs))
    rcands = r.get('row_candidates') or row_cands or [0]
    print(f"  -- candidate labelings: FOV die-types --")
    for cf in col_cands:
        for rf in rcands:
            try:
                p = fit_for_offset(det, cf, rf)
            except Exception as e:
                print(f"    (cf={cf},rf={rf}) FIT FAIL {e}"); continue
            M = p["scale"]/ra.M_ANCHOR_SCALE
            dies = fov_dies(p)
            types = sorted(set(d[2] for d in dies))
            print(f"    (col_first={cf},row_first={rf}) M={M:.3f} rmse={p['rmse_px']:.2f} "
                  f"dies={[f'{c}{chr(65+rr)}' for c,rr,_,_,_,_ in dies]}")
            print(f"        types={[TYPE_NAME[t] for t in types]}")
    return det, r


if __name__ == "__main__":
    for name, sub in CFG.items():
        run(name, sub)
