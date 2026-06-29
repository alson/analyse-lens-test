"""PROBE (task A): atlas-M vs nominal-M, and the labelling ambiguity's effect on M.

Two questions:
  Q1  Does a wrong absolute (col,row) labelling scale M by 8-29% (the handover's
      hypothesis for the atlas-vs-nominal gap)?  -> enumerate every phase-consistent
      label at the best frame, refit, look at the M spread.
  Q2  What IS the atlas-vs-nominal gap on a TRUSTWORTHY (lowest-residual, refined)
      registration, and does it track fit residual (registration error) or is it
      systematic (anchor / zoom distortion)?

Robust frame selection mirrors atlas_corner_mtf.register: try the sharpest few
frames + a spread, keep the registration with the lowest full-res refinement
residual that actually refined.  Throwaway diagnostic.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import cv2
import numpy as np

WA = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("reg_auto", WA / "reg_auto.py")
ra = importlib.util.module_from_spec(spec); spec.loader.exec_module(ra)
af = ra.af

RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
M_ANCHOR_SCALE = 1.6549  # reg_auto sweep2 (AF200 @1:1) refined scale <-> M=1.0
IMAGE_W, IMAGE_H = 8256, 5504

CONFIGS = {
    "MCON-35": (RAW / "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Olympus MCON-35" / "1_1.16" / "F8", 1/1.16),
    "6T":      (RAW / "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 6T" / "1.27_1" / "F8", 1.27),
    "5T":      (RAW / "NIKKOR Z 100-400mm f_4.5-5.6 VR S + Nikon 5T" / "1_1.19" / "F8", 1/1.19),
}


def central_lapvar(g):
    c = g[IMAGE_H//2-800:IMAGE_H//2+800, IMAGE_W//2-800:IMAGE_W//2+800]
    return cv2.Laplacian(c.astype(np.float32), cv2.CV_32F).var()


def robust_register(jpgs):
    lv = []
    for jp in jpgs:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        lv.append((central_lapvar(g) if g is not None else -1.0, jp))
    lv.sort(reverse=True)
    cand = [jp for _, jp in lv[:4]] + [jpgs[int(len(jpgs)*f)] for f in (0.35, 0.5, 0.65)]
    best = None
    for jp in dict.fromkeys(cand):
        try:
            p = ra.register_and_refine("diopter", path=str(jp), anchors=None)
        except Exception:
            continue
        if p is None or not p.get("n_refine_intersections"):
            continue
        r = p["reg_fit_rmse_px"]
        if best is None or r < best[0]:
            best = (r, jp, p)
    return best  # (rmse, frame, refined_affine) or None


def fit_for_labels(det, col_first, row_first):
    col_x, row_y = det["col_x"], det["row_y"]
    cl_list = ra._labels(col_x, col_first)
    row_rel = ra._rel_indices(row_y)
    rl_top = row_first + int(row_rel[-1])
    rl_list = [rl_top - int(r) for r in row_rel]
    pairs = [(cl_list[ci], rl_list[ri], *ra.derot_to_orig(float(xd), float(yd), det))
             for ci, xd in enumerate(col_x) for ri, yd in enumerate(row_y)]
    p = af.fit_sweep_affine(pairs, ra.ATLAS, theta_init_deg=det["tilt"], scale_init=0.5)
    return p["scale"], p["rmse_px"]


def main():
    print(f"{'cfg':<9}{'M_nom':>7}{'M_atlas':>9}{'gap%':>7}{'refrmse':>9}{'n_int':>6}"
          f"{'col_f':>14}{'row_f':>12}   label-M-spread")
    for label, (d, m_nom) in CONFIGS.items():
        jpgs = sorted(d.glob("*.jpg"))
        br = robust_register(jpgs)
        if br is None:
            print(f"{label:<9}{m_nom:7.3f}   registration FAILED"); continue
        rmse, frame, p = br
        M_atlas = p["scale"] / M_ANCHOR_SCALE
        gap = (M_atlas/m_nom - 1) * 100

        # label-ambiguity M spread (low-res refit at this frame's detection)
        det = ra.detect(str(frame))
        r = ra.register(label, det)
        col_c = r.get("col_candidates") or [r.get("col_first")]
        row_c = r.get("row_candidates") or [r.get("row_first")]
        # include the auto-picked row_first (4D-bar may pick outside candidate set)
        if r.get("row_first") is not None and r["row_first"] not in row_c:
            row_c = sorted(set(row_c) | {r["row_first"]})
        Ms = []
        for cf in col_c:
            for rf in row_c:
                try:
                    sc, _ = fit_for_labels(det, cf, rf)
                    Ms.append(sc / M_ANCHOR_SCALE)
                except Exception:
                    pass
        spread = (f"{min(Ms):.3f}-{max(Ms):.3f} ({(max(Ms)/min(Ms)-1)*100:.1f}%, "
                  f"{len(Ms)} labels)") if Ms else "n/a"
        print(f"{label:<9}{m_nom:7.3f}{M_atlas:9.3f}{gap:+7.1f}{rmse:9.2f}"
              f"{p['n_refine_intersections']:6d}"
              f"{str(p['reg_col_first'])+'('+p['reg_col_method'].split('(')[0]+')':>14}"
              f"{str(p['reg_row_first'])+'('+p['reg_row_method']+')':>12}   {spread}")


if __name__ == "__main__":
    main()
