"""Reproduce the 2:1 reg_auto failure modes + compute pitch-implied scale.

Runs the CURRENT reg_auto detect/register on the 2:1 configs and on the 4 anchor
sweeps, dumping detected scribe counts, pitches, candidate offsets, the resulting
M, residual, and the pitch-implied scale (labelling-independent).
"""
from __future__ import annotations
import importlib.util, glob, json
from pathlib import Path
import numpy as np

WA = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("reg_auto", WA / "reg_auto.py")
ra = importlib.util.module_from_spec(spec); spec.loader.exec_module(ra)

M_ANCHOR_SCALE = 1.6549
D_COL = ra.D_COL; D_ROW = ra.D_ROW

# 2:1 configs: dir + label
CFG = {
    "AF200+5T+6T_2:1": "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/Nikon AF Micro-Nikkor 200mm f_4D IF-ED + 5T + 6T/2_1/F11",
    "AF200+6T+5T_2:1": "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/Nikon AF Micro-Nikkor 200mm f_4D IF-ED + 6T + 5T/2_1/F11",
    "Sigma150+TC_2:1": "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001/2_1/F11",
    "Sigma105+TC_2:1": "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/Sigma Macro 105mm F2.8 EX DG OS HSM + TC-2001/2_1/F11",
}


def pitch_scale(det):
    """labelling-independent scale from median detected scribe pitch."""
    out = {}
    for axis, pos, atlas_mean in (("col", det["col_x"], np.mean(D_COL)),
                                   ("row", det["row_y"], np.mean(D_ROW))):
        pos = np.sort(np.asarray(pos, float))
        if pos.size < 2:
            out[axis] = None; continue
        sp = np.diff(pos)
        # robust single-pitch estimate: smallest cluster (single die), use 25th pct
        unit_ds = float(np.percentile(sp, 25))
        unit_full = unit_ds / det["ds_scale"]
        scale = unit_full / atlas_mean
        out[axis] = dict(unit_ds=unit_ds, unit_full=unit_full, scale=scale,
                         M=scale / M_ANCHOR_SCALE, n=pos.size)
    return out


def reduced_lapvar(path):
    import cv2
    g = cv2.imread(str(path), cv2.IMREAD_REDUCED_GRAYSCALE_4)
    if g is None: return -1.0
    h, w = g.shape
    c = g[h//2-200:h//2+200, w//2-200:w//2+200]
    return float(cv2.Laplacian(c.astype(np.float32), cv2.CV_32F).var())


def run_one(name, path, anchors=None):
    print(f"\n{'='*70}\n{name}\n  {Path(path).name}")
    try:
        det = ra.detect(path)
    except Exception as e:
        print(f"  DETECT FAILED: {type(e).__name__}: {e}"); return
    print(f"  tilt={det['tilt']:+.2f} ds_scale={det['ds_scale']:.4f} "
          f"n_col={len(det['col_x'])} n_row={len(det['row_y'])}")
    ps = pitch_scale(det)
    for ax in ("col", "row"):
        if ps[ax]:
            print(f"  pitch[{ax}]: unit_ds={ps[ax]['unit_ds']:.1f}px unit_full={ps[ax]['unit_full']:.0f}px "
                  f"-> scale={ps[ax]['scale']:.3f} M={ps[ax]['M']:.3f}")
    r = ra.register(name, det, anchors=anchors)
    if not r.get("success"):
        print(f"  register: FAIL ({r.get('reason')})")
        print(f"    col_cands={r.get('col_candidates')} col_method={r.get('col_method')}")
        print(f"    row_cands={r.get('row_candidates')} row_method={r.get('row_method')}")
        return
    aff = r["affine"]
    print(f"  register OK: col_first={r['col_first']}({r['col_method']}) "
          f"row_first={r['row_first']}({r['row_method']})")
    print(f"    scale={aff['scale']:.4f} M={aff['scale']/M_ANCHOR_SCALE:.4f} "
          f"lowres_rmse={aff['rmse_px']:.2f} n_pairs={r['n_pairs']}")
    try:
        pr, n_int, _ = ra.refine_full_res(path, aff)
        print(f"  refined: scale={pr['scale']:.4f} M={pr['scale']/M_ANCHOR_SCALE:.4f} "
              f"rmse={pr['rmse_px']:.2f} n_int={n_int} model={pr.get('model','sim')}")
    except Exception as e:
        print(f"  refine FAILED: {type(e).__name__}: {e}")


if __name__ == "__main__":
    print("### ANCHOR SWEEPS (baseline) ###")
    for name, (path, anchors) in ra.SWEEPS.items():
        run_one(name, path, anchors)
    print("\n\n### 2:1 CONFIGS (failing) ###")
    for name, d in CFG.items():
        jpgs = sorted(glob.glob(d + "/*.jpg"))
        if not jpgs:
            print(f"\n{name}: NO JPGS in {d}"); continue
        # sharpest frame
        lv = sorted(((reduced_lapvar(j), j) for j in jpgs), reverse=True)
        run_one(name + " [sharpest]", lv[0][1])
        # a mid frame too
        run_one(name + " [mid]", jpgs[len(jpgs)//2])
