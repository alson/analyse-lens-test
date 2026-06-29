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
      pattern), so only the WAFER OUTLINE can pick between them. fragment_-
      disambiguate() matches the observed per-cell wafer coverage against the
      fragment-outline prior (out/fragment_map.json, built by build_fragment_-
      map.py from the whole-fragment sweep1). The candidate whose nick pattern
      matches wins, by score margin. CRITICAL: _observed_cov distinguishes
      off-WAFER (jagged) from off-FRAME (FOV boundary) cells — without that,
      a column extrapolated past the frame edge looks "nicked" and the match
      fails. Column phase is taken from the wide pitch when in view, else from
      the 4D bar (its die-col is ≡0 mod 4).

  LOW-M DETECTION (sweep1). The gradient-angle tilt histogram fails at low M
  (the wafer is small in frame; the mount/fracture edge dominate), and the
  frame-relative long-line length rejects scribes that only span the wafer.
  detect() therefore falls back to _detect_lowM(): tilt by SCRIBE-ALIGNMENT
  search (maximize long-line response) + long-line length relative to the WAFER
  span. Missing scribes (low-M dropouts) are handled by GAP-AWARE labelling
  (_rel_indices / _labels): a spacing ~2x the single pitch is a gap, so labels
  skip the missing line instead of mis-numbering everything after it. (Gap-aware
  labelling also fixed sweep2, where a spurious extra row had inflated its RMSE.)

  EDGE ARTEFACTS. The rotation reflect-seam / frame boundary produce spurious
  long 'scribes' a few px from the de-rotated frame edge (e.g. sweep2's y=2 row).
  _drop_edge_peaks removes them; left in, sweep2's fit RMSE was 141 px (one bad
  line at 280 px residual dragging the whole affine), vs 56 px once dropped.

  REFINEMENT (refine_full_res). The low-res affine locates every scribe
  intersection to within tens of px, so a fast FULL-RES pass re-measures each in a
  small ROI (one full decode + a few dozen tiny de-rotated windows; no global
  full-res detection) and re-fits. Each ROI is de-rotated by the tilt so scribes
  are axis-aligned (sharp troughs); the column-mean trough gives x, the row-mean
  trough gives y, their crossing is the intersection. De-rotation is essential at
  low M (sweep1), where the tilt otherwise smears the trough below threshold.

  ACCURACY METRIC. The right measure is the refinement's INTERNAL fit residual
  (how well the many auto-detected intersections fit one grid), NOT the RMSE vs
  the 3 hand-clicked anchors — those carry their own ~few-px human click error
  and so OVERSTATE the refinement's error (they floor at ~6-10 px regardless).

  RESULT (reg_auto.py): ALL FOUR sweeps register FULLY AUTONOMOUSLY. Refined fit
  residual (R=160 ROI; the ~5deg tilt-de-rotation margin matters — R=140 was
  ~40% worse): sweep1 1.8 px (43 intersections), sweep2 4.2 px (24), sweep3
  8.5 px (7), sweep4 8.1 px (15). All were 6,000-10,000 px low-res, or total
  detection failure for sweep1. With N intersections the affine itself is pinned
  to ~residual/sqrt(N) (sweep1 ~0.3 px) — better than the manual 3-anchor method.

  RESIDUAL BUDGET (see diag_distortion_grid.py): the true-macro sweep2 (AF200)
  has ZERO lens distortion (radial k~0); the non-macro lenses DO — radial
  correction cuts sweep4's (24-120+ext) residual 8.7->5.4 px and the 100-400
  shows ~11 px edge distortion at r=3000. The atlas grid pitch ratios are
  accurate to ~0.5% vs the full-res measurement. So for non-macro lenses a
  radial-distortion term would help; for macros the residual is peak-localization
  + JPEG, near the floor. Includes the nicked-corner (sweep2) and deep-interior
  (sweep3: "absence of a nick is information") cases.

  HIGH-M ROBUSTNESS (2026-06-29). At M~2 a die is ~2475 px so the 8256x5504 frame
  holds only ~3 col x ~2 row scribes, and the bandpass long-line detector also picks
  up intra-die structure as "scribes". Two failure modes (REPORT_taskAD §A.2 / §H):
  (a) SCALE-COLLAPSE — a 6-px doublet (the detector firing on both sides of a wide
  high-M scribe) or a sub-pitch texture line becomes the smallest spacing, so gap-
  aware labelling mis-numbers and the affine shrinks scale->0 at a deceptively low
  residual (AF200+5T+6T 2:1 -> M~0.001); and (b) REG-FAIL on sharp frames (spurious
  partial col lines). Fix, all in detection/labelling (the working low/mid-M sweeps
  are untouched — they already sit on one clean lattice):
    1. _robust_unit_pitch — labelling-INDEPENDENT single-die pitch via doublet
       pre-merge + snap-quality search (the pitch that divides MOST spacings into
       near-integer steps). Gives px-per-die hence an approximate M before any label.
    2. _clean_scribes — merge doublets (0.30*unit) and drop off-lattice partial/
       texture lines against the dominant single-die lattice (>=60% on-lattice, never
       below 3 lines). E.g. Sigma150 2:1 cols [20,105,240,537,834] -> [240,537,834].
    3. register() seeds the LM solver from the pitch-implied scale (not a blind 0.5)
       and a SCALE-COLLAPSE GUARD rejects any fit with M outside [0.15,3.5] or wildly
       off the pitch anchor (scale/pitch_scale not in 0.45-2.2x). A collapse is now
       reported as failure, never silently returned.
    4. register() allows 2 lines on an axis (>=6 correspondences total) — 3 rows is
       physically unattainable at M~2 for these stacks.
  RESULT: AF200+5T+6T, AF200+6T+5T, Sigma150+TC all 2:1 now register at M~2.03-2.07,
  residual <5 px (were collapse/fail). Sigma105+TC 2:1 stays an HONEST failure
  (interior 2-row/3-col FOV, two col & two row candidates, no edge/4D-bar to
  disambiguate — correctly refused, not collapsed). See diag_highm_repro.py /
  diag_highm_fovmap.py.

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
# fragment-outline prior: canonical in atlas.json["fragment_outline"]; fall back
# to the out/ copy if an older atlas is in use.
if "fragment_outline" in ATLAS:
    FRAGMENT_MAP = ATLAS["fragment_outline"]["coverage"]
else:
    _fp = A / "out" / "fragment_map.json"
    FRAGMENT_MAP = json.load(open(_fp))["coverage"] if _fp.exists() else None
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
M_ANCHOR_SCALE = 1.6549   # atlas scale at M=1 (AF200 1:1 anchor); M = scale / this
M_BOUNDS = (0.15, 3.5)    # absolute sanity bounds on atlas M (REPORT_taskAD §A.2)


def _long_line_sig(bp, mask, axis, pct=80.0, frac=0.40):
    """Long-line opened-pixel signal. Line-length threshold L is relative to the
    WAFER SPAN along the line (not the frame) so it works at low M where the
    wafer fills only part of the frame (sweep1)."""
    from scipy.ndimage import sobel, binary_opening
    work = bp if axis == 0 else bp.T
    mwork = mask if axis == 0 else mask.T
    edges = np.abs(sobel(work, axis=1))
    em = edges > np.percentile(edges, pct)
    rows_w = np.where(mwork.any(axis=1))[0]
    span = (rows_w[-1] - rows_w[0]) if rows_w.size else work.shape[0]
    L = max(5, int(span * frac))
    return binary_opening(em, structure=np.ones((L, 1), bool)).sum(axis=0).astype(np.float32)


def _tilt_search(gray, mask, rng=8.0, coarse=0.5, fine=0.1):
    """Tilt by SCRIBE ALIGNMENT: pick the angle maximizing total long-line
    response. Robust at low M where the gradient-angle histogram fails (the
    wafer fracture edge / mount dominate it). Two-stage coarse then fine."""
    def score(t):
        der = ndi_rotate(gray, t, reshape=False, order=1, mode="reflect")
        mder = ndi_rotate(mask.astype(np.float32), t, reshape=False, order=1) > 0.5
        bp = mm.bandpass_image(der)
        return float(_long_line_sig(bp, mder, 0).sum() + _long_line_sig(bp, mder, 1).sum())
    coarse_t = max(np.arange(-rng, rng + coarse, coarse), key=score)
    return float(max(np.arange(coarse_t - coarse, coarse_t + coarse + fine, fine), key=score))


def _detect_lowM(gray_ds, ds_scale, HW, path):
    """Low-M fallback: tilt by scribe-alignment (the gradient histogram fails at
    low M) + long-line length relative to the wafer span (the wafer fills only
    part of the frame). Used when the proven path finds too few scribes (sweep1)."""
    from scipy.signal import find_peaks
    wafer, _ = wafer_mask(gray_ds)
    tilt = _tilt_search(gray_ds, wafer)
    derot = ndi_rotate(gray_ds, tilt, reshape=False, order=1, mode="reflect")
    mder = ndi_rotate(wafer.astype(np.float32), tilt, reshape=False, order=1) > 0.5
    bp = mm.bandpass_image(derot)

    Hd, Wd = derot.shape

    def peaks(axis):
        sig = _long_line_sig(bp, mder, axis)
        if sig.max() <= 0:
            return np.array([], int)
        pk = np.sort(find_peaks(sig / sig.max(), distance=6, prominence=0.08)[0])
        return _drop_edge_peaks(pk, Wd if axis == 0 else Hd)

    return dict(path=path, gray_ds=gray_ds, ds_scale=ds_scale, HW=HW, tilt=tilt, derot=derot,
                col_x=peaks(0), row_y=peaks(1))


def _drop_edge_peaks(pk, dim, margin_frac=0.015):
    """Drop peaks within a few px of the de-rotated frame edge: the rotation
    reflect-seam and frame boundary produce spurious long 'scribes' there (e.g.
    sweep2's y=2 row, which otherwise corrupts the affine fit)."""
    m = max(6, int(margin_frac * dim))
    return np.array([p for p in pk if m <= p <= dim - 1 - m], dtype=int)


def _merge_doublets_coarse(pos):
    """Merge near-duplicate lines BEFORE pitch estimation. At high M a wide scribe
    spans several px and the gradient edge detector fires on BOTH its sides ~6 px
    apart (e.g. Sigma105 2:1: cols [51,57,357,363,662,668]). Such a 6-px doublet,
    if left in, becomes the smallest spacing and masquerades as the single-die
    pitch -> scale collapses. Merge anything within 0.18x the largest spacing
    (well below one die step, well above a doublet gap)."""
    pos = np.sort(np.asarray(pos, float))
    if pos.size < 2:
        return pos
    sp = np.diff(pos)
    thr = 0.18 * float(np.max(sp))
    merged = [pos[0]]
    for x in pos[1:]:
        if x - merged[-1] < thr:
            merged[-1] = 0.5 * (merged[-1] + x)
        else:
            merged.append(x)
    return np.array(merged)


def _robust_unit_pitch(positions):
    """Single-die pitch (de-rotated ds-px) from detected line positions, robust to
    doublets, spurious partial lines, the +~20% wide super-cell column, and ~2x
    missing-scribe gaps. The true pitch divides MOST spacings into near-integer
    step counts, so pick the pitch minimizing the snap residual (mild preference
    for fewer steps so it locks onto the single-die pitch, not a sub-multiple).
    Doublets are merged first so they can't define the pitch. Returns None if
    fewer than two lines. NB this is a labelling-INDEPENDENT scale anchor: it gives
    px-per-die directly, hence an approximate M, before any (col,row) is assigned;
    this is what kills the high-M scale-collapse (REPORT_taskAD §A.2 / §H)."""
    pos = _merge_doublets_coarse(positions)
    if pos.size < 2:
        return None
    sp = np.diff(pos)
    sp = sp[sp > 1.0]
    if sp.size == 0:
        return None
    smin = float(np.min(sp))            # the single-die step (gaps/wide cols are larger)
    lo = max(8.0, 0.7 * smin)
    hi = float(np.max(sp)) * 1.10
    best = None
    for p in np.arange(lo, hi + 1.0, 1.0):
        steps = sp / p
        rounded = np.round(steps)
        valid = rounded >= 1
        if valid.sum() < max(1, 0.5 * sp.size):
            continue
        frac = np.abs(steps[valid] - rounded[valid])
        score = float(frac.mean() + 0.03 * rounded[valid].mean())
        if best is None or score < best[0]:
            best = (score, float(p))
    return best[1] if best else None


def _clean_scribes(positions, unit):
    """Drop spurious detections given the robust single-die pitch `unit`:
      (1) merge doublets — lines within 0.30*unit are one scribe (the high-M
          two-sided-edge artefact);
      (2) drop off-lattice outliers — fit the phase that puts the MOST lines on a
          single-die lattice, then drop the rest IF a clear majority (>=60%) is on
          it (e.g. Sigma150 2:1 cols [20,105,240,537,834] -> [240,537,834]). These
          off-grid lines are partial scribes / texture, and left in they mis-seed
          gap-aware labelling and collapse the affine.
    Conservative by design: never returns < 3 lines and only prunes against a
    DOMINANT lattice, so the working low/mid-M sweeps (whose detections already sit
    on one lattice, incl. the legitimate wide-column +20% and ~2x missing-scribe
    gaps) are returned unchanged."""
    pos = np.sort(np.asarray(positions, float))
    if pos.size < 3 or unit is None or unit <= 0:
        return pos
    merge_thr = 0.30 * unit
    merged = [pos[0]]
    for x in pos[1:]:
        if x - merged[-1] < merge_thr:
            merged[-1] = 0.5 * (merged[-1] + x)
        else:
            merged.append(x)
    merged = np.array(merged)
    if merged.size < 3:
        return merged
    best_phase, best_n = merged[0], -1
    for ph0 in merged:
        offs = (merged - ph0) / unit
        n_on = int(np.sum(np.abs(offs - np.round(offs)) < 0.28))
        if n_on > best_n:
            best_n, best_phase = n_on, ph0
    offs = (merged - best_phase) / unit
    on = np.abs(offs - np.round(offs)) < 0.28
    if on.sum() >= max(3, int(0.6 * merged.size)) and on.sum() < merged.size:
        return merged[on]
    return merged


def _finalize_det(det):
    """Attach robust single-die pitches and clean the scribe positions on a
    detection dict (shared by the primary and low-M detect paths). Stores
    col_unit/row_unit (de-rotated ds-px) for the labelling-independent scale
    seed/guard, and replaces col_x/row_y with the cleaned positions."""
    cu = _robust_unit_pitch(det["col_x"])
    ru = _robust_unit_pitch(det["row_y"])
    det["col_unit"], det["row_unit"] = cu, ru
    det["col_x"] = np.sort(_clean_scribes(det["col_x"], cu)).astype(float)
    det["row_y"] = np.sort(_clean_scribes(det["row_y"], ru)).astype(float)
    return det


def pitch_implied_scale(det):
    """Labelling-independent atlas scale from the detected single-die pitch.
    pitch(ds) / ds_scale = px-per-die (full res); / atlas mean pitch = atlas scale.
    Returns (scale or None, M or None). Uses whichever axis pitch is available;
    prefers the SMALLER implied scale when both exist, because a ~2x missing-scribe
    gap inflates one axis's pitch (e.g. sweep2's row gap reads M~1.9 vs the true
    1.0) whereas a wide-column only inflates ~20% — so the min is the safer, less
    gap-contaminated estimate for seeding/bounding the optimiser."""
    cands = []
    if det.get("col_unit"):
        cands.append(det["col_unit"] / det["ds_scale"] / float(np.mean(D_COL)))
    if det.get("row_unit"):
        cands.append(det["row_unit"] / det["ds_scale"] / float(np.mean(D_ROW)))
    if not cands:
        return None, None
    s = float(min(cands))
    return s, s / M_ANCHOR_SCALE


def detect(path):
    gray_ds, ds_scale, (H, W) = mm.load_gray_downscaled(path)
    # PRIMARY: proven gradient-tilt + frame-relative long-line (works at M>=1).
    tilt = mm.detect_tilt_via_gradient(gray_ds)
    derot = ndi_rotate(gray_ds, tilt, reshape=False, order=1, mode="reflect")
    Hd, Wd = derot.shape

    def peaks(extractor, dim):
        sig = extractor(mm.bandpass_image(derot))
        pk = mm.find_line_peaks(sig)
        if len(pk) < mm.RELAX_TRIGGER_N_LINES:
            pk2 = mm.find_line_peaks(extractor(mm.bandpass_image(derot), gap_bridge_px=mm.GAP_BRIDGE_PX))
            if len(pk2) > len(pk):
                pk = pk2
        return _drop_edge_peaks(np.sort(pk), dim)

    col_x = peaks(mm.extract_long_line_columns, Wd)   # x-positions
    row_y = peaks(mm.extract_long_line_rows, Hd)       # y-positions
    if len(col_x) >= 3 and len(row_y) >= 3:
        return _finalize_det(dict(path=path, gray_ds=gray_ds, ds_scale=ds_scale,
                                  HW=(H, W), tilt=tilt, derot=derot,
                                  col_x=col_x, row_y=row_y))
    # FALLBACK: low-M path (sweep1).
    return _finalize_det(_detect_lowM(gray_ds, ds_scale, (H, W), path))


def _sweep_wafer_fullres(path):
    """Full-res wafer mask (segmented at 1/4 res for speed, upsampled)."""
    from PIL import Image
    img = np.asarray(Image.open(path).convert("L"))
    small = cv2.resize(img, (img.shape[1] // 4, img.shape[0] // 4), interpolation=cv2.INTER_AREA)
    wsmall, _ = wafer_mask(small)
    return cv2.resize(wsmall, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)


def _observed_cov(wafer, p, col, row, n=5):
    """Wafer coverage over IN-FRAME samples only. Returns None for cells mostly
    outside the image: an off-FRAME cell (FOV boundary) must NOT be confused with
    an off-WAFER cell (jagged edge) — that distinction is what makes interior
    FOVs like sweep3 resolvable."""
    H, W = wafer.shape
    hits = infr = 0
    for u in np.linspace(0.15, 0.85, n):
        for v in np.linspace(0.15, 0.85, n):
            x, y = af.grid_xy(col + u, row + v, p, ATLAS)
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < W and 0 <= yi < H:
                infr += 1
                hits += int(wafer[yi, xi])
    if infr < 0.5 * n * n:
        return None
    return hits / infr


def _fragment_score(det, wafer, cf, rf):
    """Fit the affine for offset (cf,rf), then weighted MSE between observed and
    fragment-map cell coverage over in-frame cells (nicked cells weighted up)."""
    col_x, row_y = det["col_x"], det["row_y"]
    cl = _labels(col_x, cf)                       # gap-aware (handles missing scribes)
    rrel = _rel_indices(row_y)                    # image-y ascending == wafer-rl descending
    rl_top = rf + int(rrel[-1])
    rl = [rl_top - int(r) for r in rrel]
    pairs = [(cl[ci], rl[ri], *derot_to_orig(float(xd), float(yd), det))
             for ci, xd in enumerate(col_x) for ri, yd in enumerate(row_y)]
    p = af.fit_sweep_affine(pairs, ATLAS, theta_init_deg=det["tilt"], scale_init=0.5)
    H, W = wafer.shape
    diffs, wts = [], []
    for col in range(N_COL_LINES):
        for row in range(N_ROW_LINES - 1):
            x, y = af.grid_xy(col + 0.5, row + 0.5, p, ATLAS)
            if not (0 < x < W and 0 < y < H):
                continue
            m = FRAGMENT_MAP.get(f"{col},{row}")
            if m is None:
                continue
            o = _observed_cov(wafer, p, col, row)
            if o is None:                 # off-frame cell -> not a wafer-edge signal
                continue
            diffs.append((o - m) ** 2)
            wts.append(1.0 + 3.0 * (1.0 - m))
    if not diffs:
        return -1e9, p
    diffs, wts = np.array(diffs), np.array(wts)
    return -float((diffs * wts).sum() / wts.sum()), p


def fragment_disambiguate(det, col_cands, row_first, margin_thr=0.02):
    """Pick the column offset whose fragment-outline nick pattern best matches the
    observation. Returns (col_first, method) or (None, 'frag-ambiguous')."""
    if FRAGMENT_MAP is None or not col_cands:
        return None, "no-fragment-map"
    wafer = _sweep_wafer_fullres(det["path"])
    scored = sorted(((_fragment_score(det, wafer, cf, row_first)[0], cf) for cf in col_cands),
                    reverse=True)
    if len(scored) == 1:
        return scored[0][1], "fragment(single)"
    margin = scored[0][0] - scored[1][0]
    if margin >= margin_thr:
        return scored[0][1], f"fragment(margin={margin:.3f})"
    return None, f"frag-ambiguous(margin={margin:.3f})"


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


def _rel_indices(positions):
    """Relative (gap-aware) line indices for sorted detected positions. A missing
    scribe shows as a spacing ~2× the single pitch, so we round each spacing to an
    integer number of single-pitch steps. Returns an int array starting at 0; its
    last value is the SPAN (>= len-1; greater when scribes are missing)."""
    pos = np.sort(np.asarray(positions, float))
    sp = np.diff(pos)
    if sp.size == 0:
        return np.array([0])
    unit = np.percentile(sp, 20)          # ~ single pitch (robust to wide cols / gaps)
    steps = np.maximum(1, np.round(sp / max(unit, 1e-6)).astype(int))
    return np.concatenate([[0], np.cumsum(steps)])


def _labels(positions, first):
    """Absolute line indices for detected positions given the leftmost index
    `first`, gap-aware (handles missing scribes)."""
    return [int(first + r) for r in _rel_indices(positions)]


def register(name, det, anchors=None):
    col_x, row_y = det["col_x"], det["row_y"]
    res = {"name": name, "tilt": det["tilt"], "n_col": len(col_x), "n_row": len(row_y)}
    # At M~2 a die is ~2475 px so the 5504-px frame holds only ~2 row scribes (and
    # ~3 col scribes): 3 rows is unattainable for the AF200/Sigma 2:1 stacks (frame
    # scan: every frame has exactly 2 rows). Allow 2 lines on an axis as long as the
    # other axis has >=3 and the total >= 6 correspondences pins the 4-DOF affine.
    # The pitch-implied-scale seed + scale-collapse guard below keep the few-point
    # fit honest. Below 2 on either axis (or <6 points) there is no grid.
    if len(col_x) < 2 or len(row_y) < 2 or len(col_x) * len(row_y) < 6:
        res["success"] = False
        res["reason"] = f"insufficient scribes ({len(col_x)} cols, {len(row_y)} rows)"
        return res

    ev = edge_visibility(det)
    res["edge_visibility"] = ev
    EV_THR = 0.15          # a CLEAN wafer edge along the border line
    bars = detect_4d_bars(det)
    res["n_bars_detected"] = len(bars)

    # Column PHASE (mod 4): PREFER the wide-column pitch (reliable when a wide
    # column is in view); fall back to the 4D bar (its die-col is ≡0 mod 4, so
    # the col-line just left of the bar is ≡0 mod 4) when no clear wide pitch is
    # in view (e.g. sweep3's 3 short pitches).
    col_rel = _rel_indices(col_x)           # gap-aware; col_rel[-1] = span
    n_col_runs = N_COL_LINES - int(col_rel[-1])
    has_gaps = int(col_rel[-1]) > len(col_x) - 1
    sp = np.diff(np.sort(col_x))
    col_phase = None
    # Wide-pitch phase is RELIABLE only with no missing scribes (a 2-step gap
    # mimics the wide column). With gaps, leave the candidate set open and let the
    # fragment-outline match decide (low-M FOVs like sweep1 show plenty of edge).
    if not has_gaps and sp.size and sp.max() / np.median(sp) > 1.12:
        c0 = candidate_offsets(col_x, D_COL, WIDE_COL, N_COL_LINES)
        col_phase = (c0[0] % 4) if c0 else None
    if col_phase is None and not has_gaps and bars:
        bx = bars[0][0]
        left = np.where(col_x < bx)[0]
        col_phase = (-(int(left[-1]) if left.size else -1)) % 4
    col_cands = ([c for c in range(n_col_runs) if c % 4 == col_phase]
                 if col_phase is not None else list(range(n_col_runs)))

    row_pos_wafer = np.sort(-row_y.astype(float))  # wafer-y ascending proxy
    row_cands = candidate_offsets(row_pos_wafer, D_ROW, TALL_ROW, N_ROW_LINES)

    def _interior(cands, n, n_lines):
        return [c for c in cands if not _touches_edge(c, n, n_lines)]

    # --- absolute ROW offset ---
    # PRIMARY: a detected 4D bar sits in die-row D; the row-line just BELOW it
    # (next-larger image-y) is row-line 3 => pins row_first. Works for interior
    # FOVs with no wafer edge.
    row_first, row_method = None, "ambiguous"
    row_rel = _rel_indices(row_y)            # gap-aware; image-y ascending order
    votes = []
    for (bx, by) in bars:
        below = row_y[row_y > by]
        above = row_y[row_y < by]
        if below.size and above.size:
            j = int(np.where(row_y == below.min())[0][0])   # img index of line just below bar
            # rl(j) = (row_first + span) - row_rel[j]; set = 3 -> row_first
            votes.append(3 - int(row_rel[-1]) + int(row_rel[j]))
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
    else:
        # PRIMARY: match the observed corner-nick pattern to the fragment outline.
        if FRAGMENT_MAP is not None and row_first is not None:
            col_first, col_method = fragment_disambiguate(det, col_cands, row_first)
        # FALLBACK: substantial wafer edge in view, else lone interior candidate.
        if col_first is None:
            if ev["right"] >= EV_THR and ev["right"] >= ev["left"]:
                col_first, col_method = (max(col_cands) if col_cands else N_COL_LINES - len(col_x)), "right-edge"
            elif ev["left"] >= EV_THR:
                col_first, col_method = (min(col_cands) if col_cands else 0), "left-edge"
            else:
                intr = _interior(col_cands, len(col_x), N_COL_LINES)
                if len(intr) == 1:
                    col_first, col_method = intr[0], "interior-default?"
                elif col_cands:
                    col_first = None
                    col_method = col_method if col_method.startswith("frag") else f"ambiguous{col_cands}"

    res.update(col_candidates=col_cands, row_candidates=row_cands,
               col_first=col_first, col_method=col_method,
               row_first=row_first, row_method=row_method)

    if col_first is None or row_first is None:
        res["success"] = False
        res["reason"] = "absolute offset ambiguous (no usable edge / feature)"
        # still build correspondences with the GROUND-TRUTH-free best guess? no.
        return res

    # build labelled correspondences -> original image coords (gap-aware labels)
    cl_list = _labels(col_x, col_first)
    rl_top = row_first + int(row_rel[-1])
    rl_list = [rl_top - int(r) for r in row_rel]   # row_y ascending == rl descending
    pairs = []
    for ci, xd in enumerate(col_x):
        for ri, yd in enumerate(row_y):
            xo, yo = derot_to_orig(float(xd), float(yd), det)
            pairs.append((cl_list[ci], rl_list[ri], xo, yo))

    # Seed the optimiser from the labelling-INDEPENDENT pitch-implied scale (not a
    # blind 0.5): at high M, few intersections let the affine shrink scale->0 and
    # still "fit" a handful of points (REPORT_taskAD §A.2). A seed near the true
    # scale starts the LM solver in the right basin so it converges to the real
    # grid rather than the collapse minimum.
    pscale, pM = pitch_implied_scale(det)
    scale_seed = pscale if pscale else 0.5
    params = af.fit_sweep_affine(pairs, ATLAS, theta_init_deg=det["tilt"],
                                 scale_init=scale_seed)
    res["pitch_scale"] = pscale
    res["pitch_M"] = pM
    M_fit = params["scale"] / M_ANCHOR_SCALE

    # SCALE-COLLAPSE GUARD. Reject a fit whose M is outside the absolute sanity
    # bounds, OR (when we have a pitch anchor) wildly inconsistent with the
    # pitch-implied scale. The pitch anchor inflates ~2x on a missing-scribe gap
    # and ~1.2x on a wide column, so the consistency band is generous (0.45-2.2x)
    # — it catches the order-of-magnitude collapse (M~0.001 / M~0.04 / 2x mislabel)
    # without rejecting honest fits. A collapse is reported as failure, never
    # silently returned (REPORT_taskAD §A.2 / §H).
    lo, hi = M_BOUNDS
    bad = not (lo <= M_fit <= hi)
    if not bad and pscale:
        ratio = params["scale"] / pscale
        bad = not (0.45 <= ratio <= 2.2)
    if bad:
        res["success"] = False
        res["reason"] = (f"scale-collapse guard: M_fit={M_fit:.4f} "
                         f"(pitch_M={pM:.3f} scale={params['scale']:.4f} "
                         f"pitch_scale={pscale})" if pscale else
                         f"scale-collapse guard: M_fit={M_fit:.4f} out of bounds")
        res["affine"] = params
        res["fit_rmse_px"] = params["rmse_px"]
        return res

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


def _trough(prof, min_depth_std=1.0):
    """Sub-pixel position of a dark trough in a 1-D profile, or None if there
    isn't a clear one. Smooth, take the global min, require it to be meaningfully
    below the profile mean, then parabolic-interpolate."""
    if prof.size < 7:
        return None
    s = np.convolve(prof, np.ones(3) / 3.0, mode="same")
    i = int(np.argmin(s))
    if i < 2 or i > s.size - 3:
        return None
    if s[i] > s.mean() - min_depth_std * s.std():
        return None
    y0, y1, y2 = float(s[i - 1]), float(s[i]), float(s[i + 1])
    denom = y0 - 2 * y1 + y2
    off = 0.5 * (y0 - y2) / denom if abs(denom) > 1e-6 else 0.0
    return i + float(np.clip(off, -1, 1))


DIST_CENTER = (8256 / 2.0, 5504 / 2.0)   # optical centre ~ image centre
DIST_NORM = 4000.0                        # radius normalization (k1,k2 ~ O(0.01))


def _forward(prm, cl, rl):
    """Full forward model (cl,rl) -> image (x,y): similarity grid projection then
    radial distortion (k1,k2) about the image centre. prm = (theta, x0, y0, scale,
    k1, k2)."""
    th, x0, y0, s, k1, k2 = prm
    U = af._cum(D_COL, cl); V = af._cum(D_ROW, rl)
    c, sn = np.cos(th), np.sin(th)
    xu = x0 + s * (c * U + sn * V)
    yu = y0 + s * (sn * U - c * V)
    dx, dy = xu - DIST_CENTER[0], yu - DIST_CENTER[1]
    r2 = (dx * dx + dy * dy) / DIST_NORM ** 2
    f = 1.0 + k1 * r2 + k2 * r2 * r2
    return DIST_CENTER[0] + dx * f, DIST_CENTER[1] + dy * f


def grid_xy_distorted(cl, rl, p):
    """Predict image (x,y) for grid line-pair (cl,rl). Uses the radial-distortion
    model if `p` carries k1/k2 (non-macro lens), else the plain similarity."""
    if "k1" in p:
        return _forward((p["theta_rad"], p["x0_img"], p["y0_img"], p["scale"],
                         p["k1"], p["k2"]), cl, rl)
    return af.grid_xy(cl, rl, p, ATLAS)


def fit_affine_distortion(pairs, seed):
    """Least-squares fit of (theta,x0,y0,scale,k1,k2) to (cl,rl,x,y) pairs."""
    from scipy.optimize import least_squares
    s0 = [seed["theta_rad"], seed["x0_img"], seed["y0_img"], seed["scale"], 0.0, 0.0]

    def resid(prm):
        out = []
        for cl, rl, x, y in pairs:
            xp, yp = _forward(prm, cl, rl)
            out += [xp - x, yp - y]
        return np.array(out)

    sol = least_squares(resid, s0, method="lm")
    th, x0, y0, s, k1, k2 = sol.x
    return {"theta_rad": float(th), "theta_deg": float(np.degrees(th)),
            "x0_img": float(x0), "y0_img": float(y0), "scale": float(s),
            "k1": float(k1), "k2": float(k2), "model": "affine+radial",
            "rmse_px": float(np.sqrt((sol.fun ** 2).mean() * 2))}


def refine_full_res(path, p, R=160, band=100):
    """Refine a low-res affine to sub-pixel using FULL-RES data, fast: the prior
    affine `p` already locates every scribe intersection to ~tens of px, so we
    only re-measure each in a small ROI (one full decode, then tiny windows) and
    re-fit. A vertical scribe shows as the column-mean trough, a horizontal scribe
    as the row-mean trough; their crossing is the intersection. The ~theta tilt
    broadens each trough symmetrically, so its centre stays unbiased.

    Each ROI is de-rotated by the affine tilt so the scribes become axis-aligned
    (sharp deep troughs); essential at low M where the tilt otherwise smears the
    column/row-mean trough below the detection threshold (sweep1).

    Returns (refined_affine, n_intersections_used) or (p, 0) if too few found."""
    from PIL import Image
    img = np.asarray(Image.open(path).convert("L")).astype(np.float32)
    H, W = img.shape
    theta = p["theta_deg"]
    M = cv2.getRotationMatrix2D((R, R), theta, 1.0)        # de-rotate about ROI centre
    Minv = cv2.invertAffineTransform(M)
    pairs = []
    for cl in range(N_COL_LINES):
        for rl in range(N_ROW_LINES):
            xp, yp = af.grid_xy(cl, rl, p, ATLAS)
            xi, yi = int(round(xp)), int(round(yp))
            if not (R < xi < W - R and R < yi < H - R):
                continue
            roi = img[yi - R:yi + R, xi - R:xi + R]
            der = cv2.warpAffine(roi, M, (2 * R, 2 * R), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REFLECT)
            cb = der[R - band:R + band, R - band:R + band]
            xt = _trough(cb.mean(axis=0))      # vertical scribe -> x (de-rotated)
            yt = _trough(cb.mean(axis=1))      # horizontal scribe -> y (de-rotated)
            if xt is None or yt is None:
                continue
            xd, yd = (R - band) + xt, (R - band) + yt           # in de-rotated ROI
            xr = Minv[0, 0] * xd + Minv[0, 1] * yd + Minv[0, 2]  # -> original ROI
            yr = Minv[1, 0] * xd + Minv[1, 1] * yd + Minv[1, 2]
            pairs.append((cl, rl, (xi - R) + xr, (yi - R) + yr))
    if len(pairs) < 4:
        return p, 0, []
    pr = af.fit_sweep_affine(pairs, ATLAS, theta_init_deg=theta, scale_init=p["scale"])
    pr["model"] = "similarity"
    # Add a radial-distortion term when it meaningfully helps (non-macro lenses).
    # Guard against overfitting: need enough points and a real (>=20%) RMSE drop.
    # True macros get k~0 / no drop -> stay similarity; few-point sweeps skip.
    if len(pairs) >= 12:
        prd = fit_affine_distortion(pairs, pr)
        if prd["rmse_px"] <= 0.80 * pr["rmse_px"]:
            pr = prd
    return pr, len(pairs), pairs


def register_and_refine(name, path=None, anchors=None, refine=True):
    """End-to-end autonomous registration for ONE sweep, for downstream consumers
    (task15 / task17). detect -> register (absolute labelling) -> full-res
    refinement. Returns the refined affine dict, which carries the radial term
    (k1/k2) for non-macro lenses so callers should project through
    ``grid_xy_distorted``. Returns ``None`` if registration fails.

    ``path``/``anchors`` default to the built-in ``SWEEPS`` entry; ``anchors`` is
    used only for the optional cross-check RMSE inside ``register`` and is NOT
    required for autonomy. Extra provenance keys are attached:
    ``reg_method`` ('refined'/'low-res'), ``reg_col_first``/``reg_row_first`` and
    their methods, ``reg_fit_rmse_px``, and (refined) ``n_refine_intersections``.
    """
    if path is None:
        if name not in SWEEPS:
            return None
        path, anchors = SWEEPS[name]
    det = detect(path)
    r = register(name, det, anchors=anchors)
    if not r.get("success"):
        return None
    if refine:
        pr, n_int, _ = refine_full_res(path, r["affine"])
        p = dict(pr)
        # refine_full_res falls back to the low-res affine if it finds <4
        # intersections; report that honestly rather than claiming "refined".
        p["reg_method"] = "refined" if n_int else "low-res(refine-fallback)"
        p["n_refine_intersections"] = int(n_int)
    else:
        p = dict(r["affine"])
        p["reg_method"] = "low-res"
    p["reg_fit_rmse_px"] = p.get("rmse_px")
    p["reg_col_first"], p["reg_col_method"] = r["col_first"], r["col_method"]
    p["reg_row_first"], p["reg_row_method"] = r["row_first"], r["row_method"]
    return p


def _anchor_rmse(p, anchors):
    if not anchors:
        return float("nan")
    e = [np.hypot(*(np.array(grid_xy_distorted(c, r, p)) - [x, y])) for (c, r, x, y) in anchors]
    return float(np.sqrt(np.mean(np.square(e))))


def main():
    results = {}
    # refined_fit = internal fit residual of the auto-detected intersections (the
    # TRUE accuracy metric). vs_anchor = RMSE against the 3 hand-clicked anchors,
    # which is floored by human click uncertainty (~few px) and so OVERSTATES the
    # error — shown only for cross-check.
    print(f"{'sweep':<18} {'col_off':>13} {'row_off':>10} {'n_int':>6} "
          f"{'refined_fit':>12} {'(vs_anchor)':>12}")
    for name, (path, anchors) in SWEEPS.items():
        det = detect(path)
        r = register(name, det, anchors=anchors)
        results[name] = r
        if not r.get("success"):
            print(f"{name:<18}   FAIL: {r.get('reason')}")
            continue
        pr, n_int, _ = refine_full_res(path, r["affine"])
        r["affine_refined"] = pr
        r["n_refine_intersections"] = n_int
        r["refined_fit_rmse_px"] = pr.get("rmse_px")
        r["anchor_rmse_refined_px"] = _anchor_rmse(pr, anchors)
        print(f"{name:<18} {str(r['col_first'])+'('+r['col_method'].split('(')[0]+')':>13} "
              f"{str(r['row_first'])+'('+r['row_method']+')':>10} {n_int:>6} "
              f"{r['refined_fit_rmse_px']:>11.2f}p {r['anchor_rmse_refined_px']:>11.1f}p")
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
