"""Method 3 v2: register a sweep via the morphological long-line approach.

Ports the archive-2026-05/measure_wafer_squares pipeline to sweep
registration. Differences from the original:
  - Detects BOTH vertical AND horizontal long-line scribes (the original
    only needs one axis for die-period).
  - Matches detected scribe positions to the atlas's irregular super-cell
    pattern (wide col + tall row).
  - Solves a full (theta, x0, y0, scale) affine, not just a single period.

The user's suggestion: "rotate level, detect scribes, reverse-rotate the fit."
That's exactly what `detect_tilt_via_gradient → ndi_rotate → long_line_columns
→ assign atlas indices → fit affine` does.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import (binary_closing, binary_opening, gaussian_filter,
                            rotate as ndi_rotate, sobel)
from scipy.optimize import least_squares
from scipy.signal import find_peaks


ATLAS_PATH = Path(__file__).parent.parent / "atlas.json"
OUT_DIR = Path(__file__).parent.parent / "out" / "registration"

# Pipeline parameters (lifted from measure_wafer_squares with light tuning).
DOWNSAMPLE_W = 1024
EDGE_THRESHOLD_PCT = 80.0
MIN_LINE_LENGTH_FRAC = 0.40
LOW_CUT_SIGMA = 40.0
HIGH_CUT_SIGMA = 1.5
GAP_BRIDGE_PX = 15
RELAX_TRIGGER_N_LINES = 4
P_MIN = 40
P_MAX = 400


def _cum(d4, k):
    if k <= 0:
        return 0.0
    k_int = int(np.floor(k))
    frac = k - k_int
    full = k_int // 4
    rem = k_int % 4
    c = full * sum(d4) + sum(d4[:rem])
    if frac > 0:
        c += frac * d4[rem]
    return c


def load_gray_downscaled(path, target_width=DOWNSAMPLE_W):
    """Load image, convert to gray, downscale to target_width (preserve AR)."""
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
    H, W = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    scale_factor = target_width / W
    new_W = target_width
    new_H = int(H * scale_factor)
    gray_ds = cv2.resize(gray, (new_W, new_H), interpolation=cv2.INTER_AREA)
    return gray_ds.astype(np.float32), scale_factor, (H, W)


def detect_tilt_via_gradient(img, *,
                              angle_range_deg=8.0,
                              bin_width_deg=0.25,
                              edge_threshold_pct=EDGE_THRESHOLD_PCT):
    """Detect tilt by gradient-angle histogram. Returns degrees (CW positive)."""
    sx = sobel(img, axis=1)
    sy = sobel(img, axis=0)
    mag = np.hypot(sx, sy)
    thr = np.percentile(mag, edge_threshold_pct)
    strong = mag > thr
    if strong.sum() < 100:
        return 0.0
    angle = np.degrees(np.arctan2(sy[strong], sx[strong]))
    angle = (angle + 90) % 180 - 90
    bins = np.arange(-angle_range_deg, angle_range_deg + bin_width_deg, bin_width_deg)
    hist, _ = np.histogram(angle, bins=bins)
    bin_centers = bins[:-1] + bin_width_deg / 2
    # Suppress 0° spike (Lanczos aliasing artifact per docs)
    hist[np.abs(bin_centers) < bin_width_deg] = 0
    return float(bins[hist.argmax()] + bin_width_deg / 2)


def bandpass_image(img, *, low_cut_sigma=LOW_CUT_SIGMA, high_cut_sigma=HIGH_CUT_SIGMA):
    hp = img - gaussian_filter(img, sigma=low_cut_sigma)
    return gaussian_filter(hp, sigma=high_cut_sigma)


def extract_long_line_columns(img, *,
                               edge_threshold_pct=EDGE_THRESHOLD_PCT,
                               min_line_length_frac=MIN_LINE_LENGTH_FRAC,
                               gap_bridge_px=0):
    """Per-column count of pixels on a vertical edge ≥ frac × image height."""
    h, w = img.shape
    edges = np.abs(sobel(img, axis=1))
    thr = np.percentile(edges, edge_threshold_pct)
    edge_mask = edges > thr
    if gap_bridge_px > 0:
        edge_mask = binary_closing(edge_mask,
                                    structure=np.ones((gap_bridge_px, 1), dtype=bool))
    L = max(5, int(h * min_line_length_frac))
    opened = binary_opening(edge_mask, structure=np.ones((L, 1), dtype=bool))
    return opened.sum(axis=0).astype(np.float32)


def extract_long_line_rows(img, **kwargs):
    """Horizontal-scribe version: rotate 90°, run column extractor, return."""
    rotated = img.T
    return extract_long_line_columns(rotated, **kwargs)


def find_line_peaks(signal, *, p_min=P_MIN, prominence_frac=0.15):
    if signal.max() <= 0:
        return np.array([], dtype=int)
    sig_norm = signal / signal.max()
    peaks, _ = find_peaks(sig_norm, distance=max(5, p_min // 3),
                          prominence=prominence_frac)
    return peaks


def match_supercell_absolute(positions, atlas_pattern, wide_index_in_pattern,
                              n_max_atlas_indices):
    """Match positions to atlas super-cell, finding the ABSOLUTE atlas index.

    Uses the position of the wide/tall spacing (= largest in the sequence)
    to anchor the absolute index of the first detected scribe.

    Args:
      positions: detected scribe positions, sorted ascending
      atlas_pattern: 4-element pitch array (the wide/tall element is the max)
      wide_index_in_pattern: index in atlas_pattern that's wide (e.g., 0 for d_col)
      n_max_atlas_indices: total atlas indices possible (e.g., 11 for col_lines 0..10)

    Returns: list of candidates with absolute first_atlas_index, scale, rmse
    """
    if len(positions) < 3:
        return None
    positions = np.asarray(positions, dtype=np.float64)
    atlas_array = np.array(atlas_pattern, dtype=np.float64)
    spacings = np.diff(positions)
    n_spacings = len(spacings)

    # Identify which detected spacing(s) are "wide" (larger than median by > 5%)
    median_spacing = float(np.median(spacings))
    wide_threshold = 1.05 * median_spacing
    wide_spacing_idxs = [i for i, s in enumerate(spacings) if s > wide_threshold]

    candidates = []
    # Each wide-spacing detected MUST be at an atlas index where mod 4 == wide_index
    # (e.g., for cols, wide_index = 0, so the wide-spacing's LEFT scribe is at
    # col_line k where k mod 4 == 0).
    # Try each possible absolute first_atlas_index a:
    for a in range(0, n_max_atlas_indices):
        last_index = a + n_spacings  # last detected scribe is at atlas index a + n_spacings
        if last_index > n_max_atlas_indices:
            continue
        # Expected spacings for this absolute offset
        expected = np.array([atlas_array[(a + i) % 4] for i in range(n_spacings)])
        # Verify wide-spacing position(s) match
        expected_wide_idxs = [i for i, e in enumerate(expected) if (a + i) % 4 == wide_index_in_pattern]
        # Tolerate detection noise: a detected wide spacing must match exactly one expected wide
        if set(wide_spacing_idxs) != set(expected_wide_idxs):
            # Some wide-mismatch — skip
            continue
        # Fit scale
        scale = float((spacings * expected).sum() / (expected ** 2).sum())
        residuals = spacings - scale * expected
        spacing_rmse = float(np.sqrt((residuals ** 2).mean()))
        cumulative = np.cumsum([0] + list(expected))
        predicted = positions[0] + scale * cumulative
        abs_rmse = float(np.sqrt(((predicted - positions) ** 2).mean()))
        candidates.append({
            "first_atlas_index": a,
            "scale": scale,
            "spacing_rmse": spacing_rmse,
            "abs_rmse": abs_rmse,
            "n_wide_detected": len(wide_spacing_idxs),
            "n_wide_expected": len(expected_wide_idxs),
        })
    candidates.sort(key=lambda c: c["abs_rmse"])
    return candidates


def match_supercell_phase(positions, atlas_pattern):
    """Legacy phase-only matching (returns phase 0..3 ambiguity). Retained
    for fall-through when the absolute method finds no valid candidate.
    """
    if len(positions) < 3:
        return None
    positions = np.asarray(positions, dtype=np.float64)
    atlas_array = np.array(atlas_pattern, dtype=np.float64)
    spacings = np.diff(positions)
    n_spacings = len(spacings)
    candidates = []
    for phase in range(4):
        expected = np.array([atlas_array[(phase + i) % 4]
                              for i in range(n_spacings)])
        scale = float((spacings * expected).sum() / (expected ** 2).sum())
        residuals = spacings - scale * expected
        spacing_rmse = float(np.sqrt((residuals ** 2).mean()))
        cumulative = np.cumsum([0] + list(expected))
        predicted = positions[0] + scale * cumulative
        abs_rmse = float(np.sqrt(((predicted - positions) ** 2).mean()))
        candidates.append({
            "first_atlas_index": phase,
            "scale": scale,
            "spacing_rmse": spacing_rmse,
            "abs_rmse": abs_rmse,
        })
    candidates.sort(key=lambda c: c["abs_rmse"])
    return candidates


def register_sweep_morphological(sweep_path, atlas, anchor_ground_truth=None,
                                  sweep_label="sweep"):
    """Run the morphological registration pipeline."""
    print(f"  {sweep_path}")
    gray_ds, ds_scale, (H_full, W_full) = load_gray_downscaled(sweep_path)
    print(f"  Loaded: {gray_ds.shape}, ds_scale={ds_scale:.4f}")

    # 1. Detect tilt
    tilt_deg = detect_tilt_via_gradient(gray_ds)
    print(f"  Detected tilt: {tilt_deg:+.3f}°")

    # 2. De-rotate
    rotated = ndi_rotate(gray_ds, tilt_deg, reshape=False, order=1, mode="reflect")

    # 3. Bandpass
    bp = bandpass_image(rotated)

    # 4. Long-line column extraction (vertical scribes)
    col_signal = extract_long_line_columns(bp)
    col_peaks = find_line_peaks(col_signal)
    if len(col_peaks) < RELAX_TRIGGER_N_LINES:
        col_signal_relaxed = extract_long_line_columns(
            bp, gap_bridge_px=GAP_BRIDGE_PX)
        col_peaks_relaxed = find_line_peaks(col_signal_relaxed)
        if len(col_peaks_relaxed) > len(col_peaks):
            col_peaks = col_peaks_relaxed
            col_signal = col_signal_relaxed
            print(f"  Used gap-bridge relaxation for cols")

    # 5. Long-line row extraction (horizontal scribes — rotate 90° and re-extract)
    row_signal = extract_long_line_rows(bp)
    row_peaks = find_line_peaks(row_signal)
    if len(row_peaks) < RELAX_TRIGGER_N_LINES:
        row_signal_relaxed = extract_long_line_rows(bp, gap_bridge_px=GAP_BRIDGE_PX)
        row_peaks_relaxed = find_line_peaks(row_signal_relaxed)
        if len(row_peaks_relaxed) > len(row_peaks):
            row_peaks = row_peaks_relaxed
            row_signal = row_signal_relaxed
            print(f"  Used gap-bridge relaxation for rows")

    print(f"  Detected: {len(col_peaks)} vertical scribes, {len(row_peaks)} horizontal scribes")

    if len(col_peaks) < 3 or len(row_peaks) < 3:
        return {"success": False, "reason": f"only {len(col_peaks)} cols, {len(row_peaks)} rows"}

    # 6. Match super-cell phase WITH absolute index disambiguation.
    # Wafer has col_lines 0..10 (11 positions) and row_lines 0..6 (7 positions).
    # Wide col is type 0 (col_line mod 4 == 0). Tall row is type 1 (row_line mod 4 == 1).
    d_col = atlas["die_pitch_px_in_0129"]["d_col"]
    d_row = atlas["die_pitch_px_in_0129"]["d_row"]
    wide_col_idx = int(np.argmax(d_col))  # = 0
    tall_row_idx = int(np.argmax(d_row))  # = 1
    col_candidates = match_supercell_absolute(
        sorted(col_peaks.tolist()), d_col, wide_col_idx, n_max_atlas_indices=11)
    row_peaks_for_match = sorted([-p for p in row_peaks.tolist()])
    row_candidates = match_supercell_absolute(
        row_peaks_for_match, d_row, tall_row_idx, n_max_atlas_indices=7)
    # Fall through to legacy phase-only if absolute method finds nothing
    if not col_candidates:
        print("  Warning: absolute col-index method found no valid candidate, "
              "falling back to phase-only")
        col_candidates = match_supercell_phase(sorted(col_peaks.tolist()), d_col)
    if not row_candidates:
        print("  Warning: absolute row-index method found no valid candidate, "
              "falling back to phase-only")
        row_candidates = match_supercell_phase(row_peaks_for_match, d_row)

    print(f"  Col absolute-index candidates (top 3):")
    for c in col_candidates[:3]:
        idx_key = "first_atlas_index" if "first_atlas_index" in c else "phase"
        print(f"    first_atlas_idx={c[idx_key]} scale_ds={c['scale']:.3f} "
              f"abs_rmse={c['abs_rmse']:.2f} ds-px"
              + (f" wide:{c.get('n_wide_detected', '?')}/{c.get('n_wide_expected', '?')}"
                 if "n_wide_detected" in c else ""))
    print(f"  Row absolute-index candidates (top 3):")
    for c in row_candidates[:3]:
        idx_key = "first_atlas_index" if "first_atlas_index" in c else "phase"
        print(f"    first_atlas_idx={c[idx_key]} scale_ds={c['scale']:.3f} "
              f"abs_rmse={c['abs_rmse']:.2f} ds-px"
              + (f" tall:{c.get('n_wide_detected', '?')}/{c.get('n_wide_expected', '?')}"
                 if "n_wide_detected" in c else ""))

    best_col = col_candidates[0]
    best_row = row_candidates[0]
    # Compatibility shim — both methods report under different key
    col_first_atlas = best_col.get("first_atlas_index", best_col.get("phase", 0))
    row_first_atlas = best_row.get("first_atlas_index", best_row.get("phase", 0))

    # 7. Build (cl, rl, x_image, y_image) correspondence pairs.
    # Scribe positions are in DE-ROTATED ds-px coords. Need to:
    #   a. Convert ds-px back to full-res px (multiply by 1/ds_scale)
    #   b. Apply the INVERSE tilt rotation to map back to image coords
    H_ds, W_ds = gray_ds.shape
    cy_ds, cx_ds = H_ds / 2, W_ds / 2
    # Empirical sign convention: ndi_rotate(img, +tilt) un-rotates a wafer at
    # +tilt CCW (per docs). For the inverse mapping of a de-rotated point
    # back to original image, apply rotation by +tilt (NOT -tilt).
    cos_t = np.cos(np.radians(tilt_deg))
    sin_t = np.sin(np.radians(tilt_deg))
    col_peaks_sorted = sorted(col_peaks.tolist())  # image-x asc = wafer-x asc
    row_peaks_sorted = sorted(row_peaks.tolist())  # image-y asc = wafer-y DESC
    N_row = len(row_peaks_sorted)
    pairs = []
    for ci, c_pos_ds in enumerate(col_peaks_sorted):
        cl_atlas = col_first_atlas + ci
        for ri, r_pos_ds in enumerate(row_peaks_sorted):
            # Wafer-y descending in image-y ascending order → reverse rl
            rl_atlas = row_first_atlas + (N_row - 1 - ri)
            # In rotated frame: x = c_pos_ds, y = r_pos_ds
            x_rot_ds = c_pos_ds
            y_rot_ds = r_pos_ds
            # Inverse-rotate about (cx_ds, cy_ds):
            # (x', y') = R⁻¹ * (x - cx, y - cy) + (cx, cy)
            dx = x_rot_ds - cx_ds
            dy = y_rot_ds - cy_ds
            # Inverse rotation (rotate by -tilt) — but ndi_rotate uses
            # a rotation by +tilt_deg. To undo: rotate by -tilt_deg.
            # With image-y-down: rotation matrix for angle θ CCW:
            # [cos, -sin; sin, cos]. For -tilt CCW = inverse.
            x_orig_ds = cos_t * dx - sin_t * dy + cx_ds
            y_orig_ds = sin_t * dx + cos_t * dy + cy_ds
            # Up-sample to full res
            x_orig = x_orig_ds / ds_scale
            y_orig = y_orig_ds / ds_scale
            pairs.append((cl_atlas, rl_atlas, x_orig, y_orig))

    print(f"  Generated {len(pairs)} (cl, rl, x, y) correspondence pairs")

    # 8. Fit affine
    def residuals(p):
        theta, x0, y0, scale = p
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)
        out = []
        for (cl, rl, x_obs, y_obs) in pairs:
            u = scale * _cum(d_col, cl)
            v = scale * _cum(d_row, rl)
            x_pred = x0 + cos_t * u + sin_t * v
            y_pred = y0 + sin_t * u - cos_t * v
            out.append(x_pred - x_obs)
            out.append(y_pred - y_obs)
        return np.array(out)

    # Seed: tilt as theta, scale from col-phase match
    theta_init = np.radians(tilt_deg)
    scale_init = best_col["scale"] / ds_scale
    cl0, rl0, x_seed, y_seed = pairs[0]
    u_seed = scale_init * _cum(d_col, cl0)
    v_seed = scale_init * _cum(d_row, rl0)
    x0_init = x_seed - np.cos(theta_init) * u_seed - np.sin(theta_init) * v_seed
    y0_init = y_seed - np.sin(theta_init) * u_seed + np.cos(theta_init) * v_seed
    p0 = [theta_init, x0_init, y0_init, scale_init]
    sol = least_squares(residuals, p0, method="lm")
    p = sol.x
    rmse = float(np.sqrt((sol.fun ** 2).mean()))

    result = {
        "success": True,
        "tilt_detected_deg": tilt_deg,
        "theta_rad": float(p[0]), "theta_deg": float(np.degrees(p[0])),
        "x0_img": float(p[1]), "y0_img": float(p[2]),
        "scale": float(p[3]), "fit_rmse_px": rmse, "n_pairs": len(pairs),
        "n_col_scribes": int(len(col_peaks)), "n_row_scribes": int(len(row_peaks)),
        "col_first_atlas_index": col_first_atlas,
        "row_first_atlas_index": row_first_atlas,
        "col_match_rmse_ds": best_col["abs_rmse"],
        "row_match_rmse_ds": best_row["abs_rmse"],
        "n_col_candidates": len(col_candidates),
        "n_row_candidates": len(row_candidates),
    }

    if anchor_ground_truth:
        cos_t, sin_t = np.cos(p[0]), np.sin(p[0])
        errors = []
        for (cl, rl, x_obs, y_obs) in anchor_ground_truth:
            u = p[3] * _cum(d_col, cl)
            v = p[3] * _cum(d_row, rl)
            x_pred = p[1] + cos_t * u + sin_t * v
            y_pred = p[2] + sin_t * u - cos_t * v
            errors.append(float(np.hypot(x_pred - x_obs, y_pred - y_obs)))
        result["anchor_errors_px"] = errors
        result["anchor_rmse_px"] = float(np.sqrt(np.mean(np.array(errors) ** 2)))
        print(f"  Anchor RMSE: {result['anchor_rmse_px']:.1f} px (errors: {[f'{e:.0f}' for e in errors]})")

    return result


def main():
    atlas = json.load(open(ATLAS_PATH))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    sweeps = [
        ("sweep1_M0.385",
         "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
         "NIKKOR Z 100-400mm f_4.5-5.6 VR S/1_2.60/F11/"
         "00296|NIKKOR Z 100-400mm f_4.5-5.6 VR S|1_2.60|400.0 mm|F11|"
         "alm-20260208-221844-296.jpg",
         [(1, 1, 1827, 3548), (10, 1, 6078, 3901), (6, 5, 4341, 1853)]),
        ("sweep2_M1.0",
         "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
         "Nikon AF Micro-Nikkor 200mm f_4D IF-ED/1_1/F11/"
         "00353|Nikon AF Micro-Nikkor 200mm f_4D IF-ED|1_1|200.0 mm|F11|"
         "alm-20260129-162532-353.jpg",
         [(10, 2, 7136, 4742), (5, 2, 1012, 4243), (8, 5, 4831, 1009)]),
        ("sweep3_M2.0",
         "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
         "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001/2_1/F11/"
         "04069|Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001|2_1|"
         "300.0 mm|F11|alm-20260131-001833-1034.jpg",
         [(5, 4, 2094, 453), (5, 2, 1731, 5238), (7, 3, 6696, 3205)]),
        ("sweep4_newer_rig",
         "/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-12/"
         "NIKKOR Z 24-120mm f_4 S + 61mm extension (2026-05-08_201054)/"
         "f_11/step_0094_b.jpg",
         [(4, 2, 627, 4105), (8, 2, 6953, 4605), (6, 4, 4166, 1344)]),
    ]

    all_results = {}
    for sweep_label, sweep_path, anchors in sweeps:
        print(f"\n=== {sweep_label} ===")
        try:
            r = register_sweep_morphological(sweep_path, atlas,
                                              anchor_ground_truth=anchors,
                                              sweep_label=sweep_label)
        except Exception as e:
            import traceback
            r = {"success": False, "exception": str(e), "tb": traceback.format_exc()}
            print(f"  EXCEPTION: {e}")
        all_results[sweep_label] = r

    out_json = OUT_DIR / "method_morphological_results.json"
    with open(out_json, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved: {out_json}")
    print("\n=== Method 3 (morphological) summary ===")
    print(f"{'sweep':<22} {'tilt':<7} {'θ°':<7} {'scale':<8} {'anchor_RMSE':<12}")
    for label, r in all_results.items():
        if r.get("success"):
            print(f"{label:<22} {r['tilt_detected_deg']:>+5.2f}° "
                  f"{r['theta_deg']:>+5.2f}° {r['scale']:>6.3f}  "
                  f"{r.get('anchor_rmse_px', float('nan')):>8.1f} px")
        else:
            print(f"{label:<22} FAIL: {r.get('reason', r.get('exception', '?'))}")


if __name__ == "__main__":
    sys.exit(main())
