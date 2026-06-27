"""Task #2: autonomous sweep registration, rebuilt and corrected.

Reuses the PROVEN scribe detection from register_method_morphological and the
PROVEN affine solver from anchor_fit_sweep, and fixes what made the old
morphological path fail (anchor RMSE ~6000px):

  FIX 1 (geometry). Coordinate mapping de-rotated-ds -> original-image uses an
  EXPLICIT rotation with the CORRECT sign (the old code used the wrong sign;
  validated: known anchors land on detected scribes within ~0-9 ds-px with
  sign=-1, vs ~20-60 with the old +1).

  FIX 2 (labelling). Absolute (cl, rl) recovered as:
    - phase (mod 4) from the wide-column / tall-row pitch,
    - absolute offset from wafer-EDGE visibility (which physical edge is in the
      FOV pins the extreme col/row). This is the robust form of the handover's
      "whole-vs-jagged" idea: a jagged (partial) die only exists where the wafer
      edge cuts the FOV, so detecting that edge is what disambiguates.

  LIMITATION. When NO wafer edge is in the FOV (fully-interior high-M sweeps,
  e.g. sweep4), edge/jagged methods cannot disambiguate; a distinctive-feature
  anchor (e.g. the 4D bar => row D, col mod4==0) is required. We surface the
  remaining candidate set in that case.

Run:  reg_auto.py            # autonomous registration of all sweeps + validation
      reg_auto.py --validate # just the mapping/label sanity probe
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import rotate as ndi_rotate

HERE = Path(__file__).parent
A = HERE.parent
OUT = A / "out" / "diag_2026_06"
OUT.mkdir(parents=True, exist_ok=True)


def _load(modname, fname):
    spec = importlib.util.spec_from_file_location(modname, HERE / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


mm = _load("mm", "register_method_morphological.py")
af = _load("af", "anchor_fit_sweep.py")
ATLAS = json.load(open(A / "atlas.json"))
D_COL = ATLAS["die_pitch_px_in_0129"]["d_col"]
D_ROW = ATLAS["die_pitch_px_in_0129"]["d_row"]
WIDE_COL = int(np.argmax(D_COL))   # 0
TALL_ROW = int(np.argmax(D_ROW))   # 1
N_COL_LINES = 11   # cl 0..10
N_ROW_LINES = 7    # rl 0..6 (rows A..F => 6 dies)

SWEEPS = {
    "sweep1_M0.385": (
        "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
        "NIKKOR Z 100-400mm f_4.5-5.6 VR S/1_2.60/F11/"
        "00296|NIKKOR Z 100-400mm f_4.5-5.6 VR S|1_2.60|400.0 mm|F11|"
        "alm-20260208-221844-296.jpg",
        [(1, 1, 1827, 3548), (10, 1, 6078, 3901), (6, 5, 4341, 1853)]),
    "sweep2_M1.0": (
        "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
        "Nikon AF Micro-Nikkor 200mm f_4D IF-ED/1_1/F11/"
        "00353|Nikon AF Micro-Nikkor 200mm f_4D IF-ED|1_1|200.0 mm|F11|"
        "alm-20260129-162532-353.jpg",
        [(10, 2, 7136, 4742), (5, 2, 1012, 4243), (8, 5, 4831, 1009)]),
    "sweep3_M2.0": (
        "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
        "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001/2_1/F11/"
        "04069|Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001|2_1|"
        "300.0 mm|F11|alm-20260131-001833-1034.jpg",
        [(5, 4, 2094, 453), (5, 2, 1731, 5238), (7, 3, 6696, 3205)]),
    "sweep4_newer_rig": (
        "/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-12/"
        "NIKKOR Z 24-120mm f_4 S + 61mm extension (2026-05-08_201054)/"
        "f_11/step_0094_b.jpg",
        [(4, 2, 627, 4105), (8, 2, 6953, 4605), (6, 4, 4166, 1344)]),
}

ROT_SIGN = -1.0  # calibrated; see module docstring / --validate


def detect(path):
    gray_ds, ds_scale, (H, W) = mm.load_gray_downscaled(path)
    tilt = mm.detect_tilt_via_gradient(gray_ds)
    derot = ndi_rotate(gray_ds, tilt, reshape=False, order=1, mode="reflect")

    def peaks(extractor):
        sig = extractor(mm.bandpass_image(derot))
        pk = mm.find_line_peaks(sig)
        if len(pk) < mm.RELAX_TRIGGER_N_LINES:
            sig2 = extractor(mm.bandpass_image(derot), gap_bridge_px=mm.GAP_BRIDGE_PX)
            pk2 = mm.find_line_peaks(sig2)
            if len(pk2) > len(pk):
                pk = pk2
        return np.sort(pk)

    return dict(gray_ds=gray_ds, ds_scale=ds_scale, HW=(H, W), tilt=tilt, derot=derot,
                col_x=peaks(mm.extract_long_line_columns),
                row_y=peaks(mm.extract_long_line_rows))


def derot_to_orig(xd, yd, det):
    s = det["ds_scale"]
    H_ds, W_ds = det["gray_ds"].shape
    cx, cy = W_ds / 2.0, H_ds / 2.0
    th = np.radians(ROT_SIGN * det["tilt"])
    c, s_ = np.cos(th), np.sin(th)
    dx, dy = xd - cx, yd - cy
    xg = c * dx + s_ * dy + cx
    yg = -s_ * dx + c * dy + cy
    return (xg / s, yg / s)


def background_mask(derot):
    """Background = dark AND low-texture (smooth). Returns uint8 mask."""
    g = derot.astype(np.float32)
    k = 11
    mean = cv2.boxFilter(g, -1, (k, k))
    sq = cv2.boxFilter(g * g, -1, (k, k))
    std = np.sqrt(np.maximum(sq - mean * mean, 0))
    dark = g < np.percentile(g, 25)
    smooth = std < np.percentile(std, 25)
    return (dark & smooth).astype(np.uint8)


def edge_visibility(det):
    """Fraction of background in each border strip of the de-rotated frame.
    High => that wafer edge is in the FOV. Strips exclude the rotation
    border-reflect artefact by trimming the outermost few px."""
    bg = background_mask(det["derot"])
    h, w = bg.shape
    t = 6  # trim reflect seam
    bw, bh = int(0.12 * w), int(0.12 * h)
    return {
        "left": float(bg[t:-t, t:t + bw].mean()),
        "right": float(bg[t:-t, -t - bw:-t].mean()),
        "top": float(bg[t:t + bh, t:-t].mean()),
        "bottom": float(bg[-t - bh:-t, t:-t].mean()),
    }


def _phase_offset(positions, pitch4, wide_idx):
    """Given sorted line positions, return the phase p such that the leftmost
    line has index ≡ p (mod 4), using the wide pitch location."""
    if len(positions) < 2:
        return None
    sp = np.diff(positions)
    # the widest spacing's left line index ≡ wide_idx (mod 4)
    wi = int(np.argmax(sp))
    # leftmost index ≡ (wide_idx - wi) mod 4
    return (wide_idx - wi) % 4


def candidate_offsets(positions, pitch4, wide_idx, n_lines):
    """Absolute index of the leftmost detected line: all values consistent with
    phase, run length, and the 0..n_lines-1 range."""
    phase = _phase_offset(positions, pitch4, wide_idx)
    if phase is None:
        return []
    n = len(positions)
    cands = []
    for first in range(0, n_lines - n + 1):
        if first % 4 == phase:
            cands.append(first)
    return cands


def register(name, det, anchors=None, verbose=True):
    col_x, row_y = det["col_x"], det["row_y"]
    res = {"name": name, "tilt": det["tilt"], "n_col": len(col_x), "n_row": len(row_y)}
    if len(col_x) < 3 or len(row_y) < 3:
        res["success"] = False
        res["reason"] = f"insufficient scribes ({len(col_x)} cols, {len(row_y)} rows)"
        return res

    col_cands = candidate_offsets(col_x, D_COL, WIDE_COL, N_COL_LINES)
    # rows: image-y ascending = wafer-rl DESCENDING. Convert to wafer order.
    row_y_desc = row_y[::-1]                       # top-of-image first
    # tall-row pitch in wafer order: use -y so wafer-rl increases with array idx
    row_pos_wafer = np.sort(-row_y.astype(float))  # wafer-y ascending proxy
    row_cands = candidate_offsets(row_pos_wafer, D_ROW, TALL_ROW, N_ROW_LINES)

    ev = edge_visibility(det)
    res["edge_visibility"] = ev
    EV_THR = 0.06  # background fraction needed to trust an edge is in view

    def _snap(value, cands):
        """Snap an edge-derived offset to the nearest phase-consistent candidate."""
        if not cands:
            return value
        return min(cands, key=lambda c: abs(c - value))

    # --- absolute COLUMN offset: edge gives it directly (rightmost det = cl10) ---
    col_first, col_method = None, "ambiguous"
    if len(col_cands) == 1:
        col_first, col_method = col_cands[0], "unique-phase"
    elif ev["right"] >= EV_THR and ev["right"] >= ev["left"]:
        col_first = _snap((N_COL_LINES - 1) - (len(col_x) - 1), col_cands or [(N_COL_LINES-1)-(len(col_x)-1)])
        col_method = "right-edge"
    elif ev["left"] >= EV_THR:
        col_first = _snap(0, col_cands or [0])
        col_method = "left-edge"
    elif col_cands:
        col_first, col_method = None, f"ambiguous{col_cands}"

    # --- absolute ROW offset: rl increases UP the wafer (down the image y) ---
    # bottom edge in view => lowest image row (max y) is rl0/rl1.
    row_first, row_method = None, "ambiguous"
    if len(row_cands) == 1:
        row_first, row_method = row_cands[0], "unique-phase"
    elif ev["bottom"] >= EV_THR and ev["bottom"] >= ev["top"]:
        row_first = _snap(0, row_cands or [0])
        row_method = "bottom-edge"
    elif ev["top"] >= EV_THR:
        row_first = _snap((N_ROW_LINES - 1) - (len(row_y) - 1),
                          row_cands or [(N_ROW_LINES-1)-(len(row_y)-1)])
        row_method = "top-edge"
    elif row_cands:
        row_first, row_method = None, f"ambiguous{row_cands}"

    res.update(col_candidates=col_cands, row_candidates=row_cands,
               col_first=col_first, col_method=col_method,
               row_first=row_first, row_method=row_method)

    if col_first is None or row_first is None:
        res["success"] = False
        res["reason"] = "absolute offset ambiguous (no usable edge / feature)"
        # still build correspondences with the GROUND-TRUTH-free best guess? no.
        return res

    # build labelled correspondences -> original image coords
    cl_list = [col_first + i for i in range(len(col_x))]
    # row_y ascending in image == wafer rl descending; topmost image row = highest rl
    rl_top = row_first + (len(row_y) - 1)
    pairs = []
    for ci, xd in enumerate(col_x):
        for ri, yd in enumerate(row_y):  # ri=0 is topmost image row = highest rl
            rl = rl_top - ri
            xo, yo = derot_to_orig(float(xd), float(yd), det)
            pairs.append((cl_list[ci], rl, xo, yo))

    params = af.fit_sweep_affine(pairs, ATLAS, theta_init_deg=det["tilt"], scale_init=0.5)
    res["success"] = True
    res["affine"] = params
    res["fit_rmse_px"] = params["rmse_px"]
    res["n_pairs"] = len(pairs)

    if anchors:
        errs = []
        for (cl, rl, x, y) in anchors:
            xp, yp = af.grid_xy(cl, rl, params, ATLAS)
            errs.append(float(np.hypot(xp - x, yp - y)))
        res["anchor_errors_px"] = errs
        res["anchor_rmse_px"] = float(np.sqrt(np.mean(np.square(errs))))
    return res


def main():
    results = {}
    print(f"{'sweep':<18} {'tilt':>6} {'cols':>5} {'rows':>5} {'col_off':>16} "
          f"{'row_off':>16} {'fit_rmse':>9} {'anchor_rmse':>11}")
    for name, (path, anchors) in SWEEPS.items():
        det = detect(path)
        r = register(name, det, anchors=anchors)
        results[name] = r
        if r.get("success"):
            print(f"{name:<18} {r['tilt']:>+5.1f}° {r['n_col']:>5} {r['n_row']:>5} "
                  f"{str(r['col_first'])+'('+r['col_method']+')':>16} "
                  f"{str(r['row_first'])+'('+r['row_method']+')':>16} "
                  f"{r['fit_rmse_px']:>8.1f}p {r.get('anchor_rmse_px', float('nan')):>10.1f}p")
        else:
            print(f"{name:<18} {r.get('tilt', 0):>+5.1f}° {r.get('n_col','?'):>5} "
                  f"{r.get('n_row','?'):>5}   FAIL: {r.get('reason')}")
    json.dump(results, open(OUT / "reg_auto_results.json", "w"), indent=1, default=float)
    print(f"\nsaved {OUT/'reg_auto_results.json'}")


def oracle():
    """Prove FIX 1 (geometry): auto-detect scribes, assign labels via the KNOWN
    affine (anchor_fit_params), then RE-FIT from scratch using only the
    auto-detected scribes. Low anchor-RMSE => the detection + coordinate mapping
    are correct, isolating the geometry fix from the (harder) autonomous-label
    problem. Compares against the old morphological path's anchor-RMSE."""
    gt = json.load(open(A / "out" / "sweep_anchors" / "anchor_fit_params.json"))
    old = {}
    op = A / "out" / "registration" / "method_morphological_results.json"
    if op.exists():
        old = json.load(open(op))
    print(f"{'sweep':<18} {'auto cols/rows':>14} {'oracle fit_rmse':>16} "
          f"{'oracle anchor_rmse':>19} {'OLD morph anchor_rmse':>22}")
    for name, (path, anchors) in SWEEPS.items():
        det = detect(path)
        p = gt.get(name)
        if not p:
            continue
        # snap each detected scribe to nearest cl / rl under the known affine
        # invert: find cl such that grid_xy(cl, rl0) matches. Easier: search.
        def nearest_cl(xo, yo):
            best, bd = None, 1e18
            for cl in range(0, N_COL_LINES):
                xg, yg = af.grid_xy(cl, 0, p, ATLAS)
                # distance along col direction only via x is messy; use full grid search over rl too
            # do a 2D search:
            best = None; bd = 1e18
            for cl in range(0, N_COL_LINES):
                for rl in range(0, N_ROW_LINES):
                    xg, yg = af.grid_xy(cl, rl, p, ATLAS)
                    d = (xg-xo)**2 + (yg-yo)**2
                    if d < bd:
                        bd, best = d, (cl, rl)
            return best
        col_lbl = {}
        for xd in det["col_x"]:
            xo, yo = derot_to_orig(float(xd), float(det["row_y"][len(det["row_y"])//2]), det)
            col_lbl[float(xd)] = nearest_cl(xo, yo)[0]
        row_lbl = {}
        for yd in det["row_y"]:
            xo, yo = derot_to_orig(float(det["col_x"][len(det["col_x"])//2]), float(yd), det)
            row_lbl[float(yd)] = nearest_cl(xo, yo)[1]
        pairs = []
        for xd in det["col_x"]:
            for yd in det["row_y"]:
                xo, yo = derot_to_orig(float(xd), float(yd), det)
                pairs.append((col_lbl[float(xd)], row_lbl[float(yd)], xo, yo))
        if len(pairs) < 3:
            print(f"{name:<18}  insufficient scribes"); continue
        params = af.fit_sweep_affine(pairs, ATLAS, theta_init_deg=det["tilt"], scale_init=0.5)
        errs = [np.hypot(*(np.array(af.grid_xy(cl, rl, params, ATLAS)) - [x, y]))
                for (cl, rl, x, y) in anchors]
        arm = float(np.sqrt(np.mean(np.square(errs))))
        old_arm = old.get(name, {}).get("anchor_rmse_px", float("nan"))
        print(f"{name:<18} {str(len(det['col_x']))+'/'+str(len(det['row_y'])):>14} "
              f"{params['rmse_px']:>15.1f}p {arm:>18.1f}p {old_arm:>21.1f}p")


if __name__ == "__main__":
    if "--oracle" in sys.argv:
        oracle()
    elif "--validate" in sys.argv:
        # quick mapping sanity: anchors -> derot, nearest scribe distance
        for name, (path, anchors) in SWEEPS.items():
            det = detect(path)
            print(f"\n{name}: tilt={det['tilt']:+.2f}")
            for (cl, rl, x, y) in anchors:
                # forward map orig->derot by inverting derot_to_orig numerically:
                s = det["ds_scale"]; H_ds, W_ds = det["gray_ds"].shape
                cx, cy = W_ds/2, H_ds/2; th = np.radians(ROT_SIGN*det["tilt"])
                c, s_ = np.cos(th), np.sin(th)
                xg, yg = x*s, y*s
                dx, dy = xg-cx, yg-cy
                xd = c*dx - s_*dy + cx; yd = s_*dx + c*dy + cy
                dc = min(abs(det['col_x']-xd)) if len(det['col_x']) else -1
                dr = min(abs(det['row_y']-yd)) if len(det['row_y']) else -1
                print(f"  ({cl},{rl}) derot=({xd:.0f},{yd:.0f}) d_col={dc:.0f} d_row={dr:.0f}")
    else:
        main()
