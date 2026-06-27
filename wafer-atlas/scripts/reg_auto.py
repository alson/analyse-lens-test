"""Task #2: autonomous sweep registration, rebuilt and corrected.

Reuses the PROVEN scribe detection from register_method_morphological and the
PROVEN affine solver from anchor_fit_sweep, and fixes what made the old
morphological path fail (anchor RMSE ~6000px):

  FIX 1 (geometry). Coordinate mapping de-rotated-ds -> original-image uses an
  EXPLICIT rotation with the CORRECT sign (the old code used the wrong sign;
  validated: known anchors land on detected scribes within ~0-9 ds-px with
  sign=-1, vs ~20-60 with the old +1).

  FIX 2 (labelling). Absolute (cl, rl) recovered as:
    - ROW: a detected 4D bar sits in die-row D (the only row ≡3 mod 4 in A-F),
      so the row-line just below it is row-line 3 => pins row_first. This is a
      DISTINCTIVE-FEATURE anchor and works for fully-interior FOVs (sweep4),
      which the handover's "whole-vs-jagged" plan could not. Verified correct on
      sweeps 2/3/4 (all row_first=2).
    - COL: the two phase-consistent candidates are type-IDENTICAL (same mod-4
      pattern), so the 4D bar cannot pick between them and only the physical
      wafer edge can. `wafer_mask()` segments the wafer (textured region) on the
      full ORIGINAL image and reports which frame side the fracture edge is in
      view on; a substantial edge commits that side, a confirmed-interior FOV
      (no edge) takes the lone interior candidate, else low-confidence
      ("interior-default?") + the candidate set is reported.

  RESULT (reg_auto.py, vs known anchors): sweep4 fully autonomous at 37 px
  (was 6,377 px); rows correct on sweeps 2/3/4. The wafer-edge segmenter is now
  reliable (no false positives: interior sweeps 3/4 report no edge; sweep1's
  substantial edge is detected) so sweep4 resolves its column principledly as a
  confirmed-interior FOV. Two columns still don't resolve, for reasons that are
  NOT the registration math:
    * sweep2 — the fragment fills the FOV leaving only tiny corner nicks, so no
      substantial edge is in view (an information limit). Resolving it needs the
      fragment-shape / whole-vs-jagged PRIOR (match which corners are nicked to
      the wafer's known outline), not better segmentation.
    * sweep3 — detection-degenerate (3 cols / 3 rows, no wide pitch in view), so
      even the phase is under-determined.

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


def wafer_mask(gray_ds):
    """Segment the WAFER (textured) region on the full ORIGINAL image (no
    cropping, no de-rotation reflect artefact). The wafer fracture edge is the
    boundary of this region that sits inside the frame; off-wafer is the
    border-connected complement. Interior smooth die regions are filled by
    flood-fill-from-border so they are NOT mistaken for background.

    Returns (wafer_filled uint8, off_wafer uint8)."""
    g = gray_ds.astype(np.float32)
    k = 13
    mean = cv2.boxFilter(g, -1, (k, k))
    sq = cv2.boxFilter(g * g, -1, (k, k))
    std = np.sqrt(np.maximum(sq - mean * mean, 0))
    textured = (std > max(4.0, np.percentile(std, 35))).astype(np.uint8)
    # bridge thin scribe gaps (~5 px), NOT the larger off-wafer gaps
    textured = cv2.morphologyEx(textured, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    textured = cv2.morphologyEx(textured, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(textured, 8)
    if n <= 1:
        return textured, (1 - textured).astype(np.uint8)
    wafer = (lbl == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    h, w = wafer.shape
    ff = (1 - wafer).astype(np.uint8)
    cv2.floodFill(ff, np.zeros((h + 2, w + 2), np.uint8), (0, 0), 0)  # border-connected -> 0
    wafer_filled = (wafer | ff).astype(np.uint8)      # ff now = interior holes
    return wafer_filled, (1 - wafer_filled).astype(np.uint8)


def edge_visibility(det):
    """Per-frame-side wafer-edge-in-view signal = 1 - (fraction of that side's
    border covered by wafer). High => the wafer's fracture edge is in view on
    that side. Computed on the full original image."""
    wafer, _ = wafer_mask(det["gray_ds"])
    h, w = wafer.shape
    b = max(3, int(0.02 * min(h, w)))
    return {
        "left": 1.0 - float(wafer[:, :b].mean()),
        "right": 1.0 - float(wafer[:, -b:].mean()),
        "top": 1.0 - float(wafer[:b, :].mean()),
        "bottom": 1.0 - float(wafer[-b:, :].mean()),
    }


def detect_4d_bars(det):
    """Detect isolated dark vertical bars (the 4D-type slanted-edge feature) in
    the de-rotated frame. The 4D bar uniquely identifies row D (the only row ≡3
    mod 4 in A–F) and a col ≡0 mod 4, so it pins the absolute offset even for
    fully-interior FOVs that have no wafer edge. Returns [(cx, cy), ...]."""
    col_x, row_y = det["col_x"], det["row_y"]
    if len(col_x) < 2 or len(row_y) < 2:
        return []
    col_pitch = float(np.median(np.diff(col_x)))
    row_pitch = float(np.median(np.diff(row_y)))
    exp_w = 0.122 * col_pitch    # atlas 4D bbox_uv width  ~0.122 of die
    exp_h = 0.235 * row_pitch    # atlas 4D bbox_uv height ~0.235 of die
    g = det["derot"].astype(np.uint8)
    thr, _ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark = cv2.morphologyEx((g < thr).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, lbl, stats, cent = cv2.connectedComponentsWithStats(dark, 8)
    bars = []
    for i in range(1, n):
        w = stats[i, cv2.CC_STAT_WIDTH]; h = stats[i, cv2.CC_STAT_HEIGHT]
        area = stats[i, cv2.CC_STAT_AREA]
        if h <= w:                                   # must be taller than wide
            continue
        if not (0.4 * exp_w < w < 2.4 * exp_w and 0.4 * exp_h < h < 2.4 * exp_h):
            continue
        if area / (w * h) < 0.55:                     # solid rectangle, not a blob cluster
            continue
        bars.append((float(cent[i][0]), float(cent[i][1])))
    return bars


def _touches_edge(first, n, n_lines):
    """Does a run of n consecutive lines starting at `first` include a wafer
    edge line (0 or n_lines-1, i.e. the jagged extremes)?"""
    return first == 0 or (first + n - 1) == (n_lines - 1)


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
    EV_THR = 0.15          # a CLEAN wafer edge along the border line
    bars = detect_4d_bars(det)
    res["n_bars_detected"] = len(bars)

    def _interior(cands, n, n_lines):
        return [c for c in cands if not _touches_edge(c, n, n_lines)]

    # --- absolute ROW offset ---
    # PRIMARY: a detected 4D bar sits in die-row D; the row-line just BELOW it
    # (next-larger image-y) is row-line 3 => pins row_first. Works for interior
    # FOVs with no wafer edge.
    row_first, row_method = None, "ambiguous"
    votes = []
    for (bx, by) in bars:
        below = row_y[row_y > by]
        above = row_y[row_y < by]
        if below.size and above.size:
            j = int(np.where(row_y == below.min())[0][0])   # img index of line just below bar
            votes.append(j + 4 - len(row_y))                # = row_first that makes that line rl3
    if votes:
        vals, counts = np.unique(votes, return_counts=True)
        row_first, row_method = int(vals[np.argmax(counts)]), "4D-bar"
    elif len(row_cands) == 1:
        row_first, row_method = row_cands[0], "unique-phase"
    elif ev["bottom"] >= EV_THR and ev["bottom"] >= ev["top"]:
        row_first, row_method = (min(row_cands) if row_cands else 0), "bottom-edge"
    elif ev["top"] >= EV_THR:
        row_first, row_method = (max(row_cands) if row_cands else N_ROW_LINES - len(row_y)), "top-edge"
    else:
        intr = _interior(row_cands, len(row_y), N_ROW_LINES)
        if len(intr) == 1:
            row_first, row_method = intr[0], "interior-default"
        elif row_cands:
            row_first, row_method = None, f"ambiguous{row_cands}"

    # --- absolute COLUMN offset ---
    # A 4D bar's left col-line is ≡0 mod 4, but the two phase-consistent
    # candidate positions have the SAME mod-4 pattern (type-identical), so the
    # bar can't pick between them. Use the wafer edge; if none is in view the
    # FOV must be the interior candidate (not touching col 0 / col 10).
    col_first, col_method = None, "ambiguous"
    if len(col_cands) == 1:
        col_first, col_method = col_cands[0], "unique-phase"
    elif ev["right"] >= EV_THR and ev["right"] >= ev["left"]:
        col_first, col_method = (max(col_cands) if col_cands else N_COL_LINES - len(col_x)), "right-edge"
    elif ev["left"] >= EV_THR:
        col_first, col_method = (min(col_cands) if col_cands else 0), "left-edge"
    else:
        intr = _interior(col_cands, len(col_x), N_COL_LINES)
        if len(intr) == 1:
            # plausible but UNVERIFIED: a true edge-touching FOV with an
            # undetected small corner cut would also land here. Low confidence.
            col_first, col_method = intr[0], "interior-default?"
        elif col_cands:
            col_first, col_method = None, f"ambiguous{col_cands}"

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
