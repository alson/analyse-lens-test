"""Method 3: register a sweep via scribe-line detection + super-cell fit.

Pipeline:
  1. Downsample sweep + Canny edge detection.
  2. Probabilistic Hough → all line segments above a length threshold.
  3. Filter to "near-axis" angles using the rotation prior (~4.7° CW)
     — keep two families (vertical-scribe-like and horizontal-scribe-like).
  4. For each family, project each line's midpoint onto the cross-axis
     unit vector → 1-D positions of all detected scribe lines.
  5. Cluster nearby positions (de-dup multiple Hough hits on the same scribe).
  6. The set of unique positions has the wafer's irregular super-cell
     spacing signature: (one ~1.19× wider element every 4 in col,
     one ~1.19× taller element every 4 in row).
  7. Identify the wide-element phase by sliding the super-cell pattern
     over the observed spacings; pick the alignment with the lowest
     residual.
  8. Assign atlas col_line / row_line indices to each detected position
     based on the chosen phase.
  9. Solve (theta, x0, y0, scale) by least squares.

Falls back gracefully when fewer than ~1 super-cell is visible (high-M
sweeps): if we don't detect at least 5 lines in either direction, signal
"can't use scribe method".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.optimize import least_squares
from skimage.feature import canny
from skimage.transform import probabilistic_hough_line


ATLAS_PATH = Path(__file__).parent.parent / "atlas.json"
OUT_DIR = Path(__file__).parent.parent / "out" / "registration"

# Downsample factor
DS = 4

# Rotation prior — wafer's QR-plate-fixed angle observed at 4.3-4.8° CW across sweeps
THETA_PRIOR_DEG = 4.5
THETA_TOLERANCE_DEG = 3.0  # accept lines within ±3° of prior axes

# Hough parameters (tune for downsampled wafer scale)
CANNY_SIGMA = 1.0
HOUGH_THRESHOLD = 80
HOUGH_MIN_LENGTH = 100
HOUGH_MAX_GAP = 25


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


def _silicon_mask(rgb):
    """Loose silicon mask — chromatic only, no brightness filter."""
    R, G, B = rgb[..., 0].astype(int), rgb[..., 1].astype(int), rgb[..., 2].astype(int)
    chroma_green = G - 0.5 * (R + B)
    sat = rgb.max(-1) - rgb.min(-1)
    mask = (chroma_green < 25) & ~((rgb.max(-1) > 200) & (sat < 30))
    return mask


def detect_scribe_lines(sweep_gray_ds, mask_ds, theta_prior_rad,
                        tolerance_rad):
    """Hough line detection → return lists of (vertical, horizontal) line midpoints.

    Each midpoint is (x_ds, y_ds) and angle is in radians.
    Vertical lines: angle near theta_prior + 90°. Horizontal: near theta_prior.
    """
    edges = canny(sweep_gray_ds.astype(np.float32) / 255.0, sigma=CANNY_SIGMA,
                  low_threshold=0.05, high_threshold=0.15)
    edges &= mask_ds
    print(f"  Canny edges: {edges.sum()} pixels")
    lines = probabilistic_hough_line(
        edges, threshold=HOUGH_THRESHOLD,
        line_length=HOUGH_MIN_LENGTH, line_gap=HOUGH_MAX_GAP)
    print(f"  Hough lines: {len(lines)}")
    vert, horiz = [], []
    for (x0, y0), (x1, y1) in lines:
        # Angle of line direction
        ang = np.arctan2(y1 - y0, x1 - x0)
        # Fold to [-π/2, π/2)
        ang = (ang + np.pi / 2) % np.pi - np.pi / 2
        # Horizontal scribe direction = +x-rotated-by-theta = (cos θ, sin θ)
        # angle ≈ θ_prior, fold same way
        prior_h = (theta_prior_rad + np.pi / 2) % np.pi - np.pi / 2
        # Vertical scribe direction = +y-rotated = (sin θ, -cos θ)
        # angle ≈ θ_prior + π/2 = θ_prior - π/2 (mod π)
        prior_v = (theta_prior_rad - np.pi / 2 + np.pi / 2) % np.pi - np.pi / 2  # = θ_prior
        # Wait this isn't right. Vertical line has angle ±90° from horizontal.
        # In folded [-π/2, π/2), horizontal-ish lines have ang near 0,
        # vertical-ish lines have ang near ±π/2 which folds to ∓π/2 — at the boundary.
        # Use absolute angle relative to two axes:
        # h-axis angle = theta_prior (line direction is along scribe)
        # v-axis angle = theta_prior + π/2
        # Use unfolded difference, then take cos of difference for similarity
        h_diff = abs(((ang - theta_prior_rad + np.pi / 2) % np.pi) - np.pi / 2)
        v_diff = abs(((ang - theta_prior_rad - np.pi / 2 + np.pi / 2) % np.pi) - np.pi / 2)
        # Wait this is getting tangled. Let me just compute directly:
        # h scribe direction makes angle θ with image +x. So line angle ≈ θ.
        # v scribe direction makes angle θ + π/2.
        # In [-π/2, π/2), "≈ θ" means dist to θ small, "≈ θ + π/2" means dist to (θ - π/2) small after folding
        h_ang = ((ang - theta_prior_rad) + np.pi / 2) % np.pi - np.pi / 2
        v_target = theta_prior_rad - np.pi / 2  # = θ - π/2, folded angle of v scribe
        v_ang = ((ang - v_target) + np.pi / 2) % np.pi - np.pi / 2
        if abs(h_ang) <= tolerance_rad:
            horiz.append((((x0 + x1) / 2, (y0 + y1) / 2), ang))
        elif abs(v_ang) <= tolerance_rad:
            vert.append((((x0 + x1) / 2, (y0 + y1) / 2), ang))
    print(f"  Filtered: {len(horiz)} horizontal-family, {len(vert)} vertical-family")
    return vert, horiz


def cluster_positions_1d(positions, tolerance=8.0):
    """Cluster 1-D positions; return cluster centroids sorted ascending."""
    if not positions:
        return []
    positions = sorted(positions)
    clusters = [[positions[0]]]
    for p in positions[1:]:
        if p - clusters[-1][-1] <= tolerance:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return [float(np.mean(c)) for c in clusters]


def project_lines_to_axis(lines, theta_prior_rad, axis="vertical"):
    """Project line midpoints onto the cross-axis to get 1-D positions.

    For 'vertical' scribes (i.e. running along the y-direction of the wafer),
    the position is the projection onto the wafer's +x axis (perpendicular to the scribe).
    Wafer +x in image coords = (cos θ, sin θ).
    """
    if axis == "vertical":
        # +x axis in image
        ux = np.cos(theta_prior_rad)
        uy = np.sin(theta_prior_rad)
    else:
        # +y axis (wafer "up") in image = (sin θ, -cos θ)
        ux = np.sin(theta_prior_rad)
        uy = -np.cos(theta_prior_rad)
    return [m[0] * ux + m[1] * uy for (m, ang) in lines]


def match_supercell_phase(positions, atlas_pattern):
    """Try all 4 phase offsets; pick the one with smallest fit residual.

    Returns (phase, scale, rmse, predicted_positions) where:
      - phase: which atlas index the FIRST detected position is
      - scale: pixels per atlas unit
      - rmse: residual

    Also returns runner_up (second-best phase) for sanity.
    """
    if len(positions) < 3:
        return None
    positions = np.asarray(positions)
    atlas_array = np.array(atlas_pattern, dtype=np.float64)
    spacings = np.diff(positions)

    candidates = []
    for phase in range(4):
        expected = np.array([atlas_array[(phase + i) % 4]
                              for i in range(len(spacings))])
        scale = float((spacings * expected).sum() / (expected ** 2).sum())
        residuals = spacings - scale * expected
        rmse = float(np.sqrt((residuals ** 2).mean()))
        # Also fit the absolute positions: position[i] = position[0] + scale * sum(expected[0..i-1])
        cumulative = np.cumsum([0] + list(expected))
        predicted = positions[0] + scale * cumulative
        abs_rmse = float(np.sqrt(((predicted - positions) ** 2).mean()))
        candidates.append({
            "phase": phase, "scale": scale,
            "spacing_rmse": rmse, "abs_rmse": abs_rmse,
            "predicted": predicted.tolist(),
        })
    candidates.sort(key=lambda c: c["abs_rmse"])
    return candidates


def register_sweep_scribelines(sweep_path, atlas, anchor_ground_truth=None,
                                sweep_label="sweep"):
    rgb = np.asarray(Image.open(sweep_path).convert("RGB"), dtype=np.uint8)
    print(f"  Sweep image: {rgb.shape}")
    mask = _silicon_mask(rgb)
    print(f"  Silicon mask: {100*mask.mean():.1f}% of frame")

    # Downsample
    rgb_ds = cv2.resize(rgb, (rgb.shape[1] // DS, rgb.shape[0] // DS),
                        interpolation=cv2.INTER_AREA)
    mask_ds = cv2.resize(mask.astype(np.uint8), (rgb.shape[1] // DS, rgb.shape[0] // DS),
                         interpolation=cv2.INTER_NEAREST) > 0
    gray_ds = cv2.cvtColor(rgb_ds, cv2.COLOR_RGB2GRAY)

    theta_rad = np.radians(THETA_PRIOR_DEG)
    tolerance = np.radians(THETA_TOLERANCE_DEG)

    vert_lines, horiz_lines = detect_scribe_lines(gray_ds, mask_ds, theta_rad, tolerance)
    if len(vert_lines) < 3 or len(horiz_lines) < 3:
        return {"success": False,
                "reason": f"only {len(vert_lines)} vertical, {len(horiz_lines)} horizontal lines"}

    # Project each line onto the cross-axis
    vert_positions_raw = project_lines_to_axis(vert_lines, theta_rad, "vertical")
    horiz_positions_raw = project_lines_to_axis(horiz_lines, theta_rad, "horizontal")

    # Cluster within 8 ds-px tolerance
    vert_positions = cluster_positions_1d(vert_positions_raw, tolerance=8.0)
    horiz_positions = cluster_positions_1d(horiz_positions_raw, tolerance=8.0)
    print(f"  Unique scribe positions: {len(vert_positions)} vertical, {len(horiz_positions)} horizontal")

    if len(vert_positions) < 3 or len(horiz_positions) < 3:
        return {"success": False, "reason": "not enough unique positions after clustering"}

    # Match super-cell phase
    d_col = atlas["die_pitch_px_in_0129"]["d_col"]
    d_row = atlas["die_pitch_px_in_0129"]["d_row"]
    col_candidates = match_supercell_phase(vert_positions, d_col)
    row_candidates = match_supercell_phase(horiz_positions, d_row)
    if col_candidates is None or row_candidates is None:
        return {"success": False, "reason": "phase match failed"}

    print(f"  Top col phase candidates (sorted by abs_rmse):")
    for c in col_candidates[:2]:
        print(f"    phase={c['phase']}, scale_ds={c['scale']:.3f}, abs_rmse={c['abs_rmse']:.2f}")
    print(f"  Top row phase candidates:")
    for c in row_candidates[:2]:
        print(f"    phase={c['phase']}, scale_ds={c['scale']:.3f}, abs_rmse={c['abs_rmse']:.2f}")

    best_col = col_candidates[0]
    best_row = row_candidates[0]

    # Build correspondences: detected positions → atlas col_line / row_line
    # Each cross of a vertical scribe (cl_line) with a horizontal scribe (rl_line)
    # gives a 2D correspondence point.
    # Position in ds-px in rotated wafer-frame:
    #   vert position = projection onto wafer +x at angle theta
    #   horiz position = projection onto wafer +y at angle theta
    # To convert back to image (x, y) at the line midpoint, we'd need both axes.
    # Simpler: for each (v_pos, h_pos) pair, compute the image (x, y) at the
    # intersection point on the rotated-wafer frame: that's the point with
    # wafer-frame coords (v_pos, h_pos) at scale 1, where wafer +x is (cos θ, sin θ).
    cos_t = np.cos(theta_rad)
    sin_t = np.sin(theta_rad)
    pairs = []  # (cl_atlas, rl_atlas, x_orig_img, y_orig_img)
    for i, v_pos in enumerate(vert_positions):
        cl_atlas = best_col["phase"] + i
        for j, h_pos in enumerate(horiz_positions):
            rl_atlas = best_row["phase"] + j
            # In rotated-DS frame: x_rotated_ds = v_pos, y_rotated_ds = -h_pos (wafer +y = image -y)
            # But this is in DS-frame. To map to full-res image:
            #   x_orig = v_pos * cos_t - (-h_pos) * sin_t = v_pos * cos_t + h_pos * sin_t (in DS)
            #   y_orig = v_pos * sin_t + (-h_pos) * cos_t = v_pos * sin_t - h_pos * cos_t (in DS)
            # Then multiply by DS to get full-res.
            # Actually we projected onto wafer's +x and +y axes:
            #   v_pos = (x_img * cos θ + y_img * sin θ) is the wafer +x coordinate
            #   h_pos = (x_img * sin θ - y_img * cos θ) is the wafer +y coordinate
            # Inverting:
            #   x_img = v_pos * cos θ + h_pos * sin θ
            #   y_img = v_pos * sin θ - h_pos * cos θ
            x_ds = v_pos * cos_t + h_pos * sin_t
            y_ds = v_pos * sin_t - h_pos * cos_t
            x_orig = x_ds * DS
            y_orig = y_ds * DS
            pairs.append((cl_atlas, rl_atlas, x_orig, y_orig))

    print(f"  Generated {len(pairs)} (cl, rl, x, y) correspondence pairs")

    # Fit affine
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

    cl0, rl0, x_seed, y_seed = pairs[0]
    scale_init = best_col["scale"] * DS / d_col[best_col["phase"] % 4]
    theta_init = np.radians(THETA_PRIOR_DEG)
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
        "theta_rad": float(p[0]), "theta_deg": float(np.degrees(p[0])),
        "x0_img": float(p[1]), "y0_img": float(p[2]),
        "scale": float(p[3]), "fit_rmse_px": rmse, "n_pairs": len(pairs),
        "col_phase": best_col["phase"], "row_phase": best_row["phase"],
        "col_phase_rmse": best_col["abs_rmse"], "row_phase_rmse": best_row["abs_rmse"],
        "n_vert_scribes": len(vert_positions), "n_horiz_scribes": len(horiz_positions),
    }

    if anchor_ground_truth:
        theta = result["theta_rad"]
        cos_t, sin_t = np.cos(theta), np.sin(theta)
        errors = []
        for (cl, rl, x_obs, y_obs) in anchor_ground_truth:
            u = result["scale"] * _cum(d_col, cl)
            v = result["scale"] * _cum(d_row, rl)
            x_pred = result["x0_img"] + cos_t * u + sin_t * v
            y_pred = result["y0_img"] + sin_t * u - cos_t * v
            err = np.hypot(x_pred - x_obs, y_pred - y_obs)
            errors.append(err)
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
            r = register_sweep_scribelines(sweep_path, atlas,
                                             anchor_ground_truth=anchors,
                                             sweep_label=sweep_label)
        except Exception as e:
            r = {"success": False, "exception": str(e)}
            print(f"  Exception: {e}")
        all_results[sweep_label] = r

    out_json = OUT_DIR / "method_scribelines_results.json"
    with open(out_json, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved: {out_json}")

    print("\n=== Method 3 (scribe-lines) summary ===")
    print(f"{'sweep':<22} {'success':<8} {'θ°':<8} {'scale':<8} {'anchor_RMSE':<14}")
    for label, r in all_results.items():
        if r.get("success"):
            print(f"{label:<22} ✓        {r['theta_deg']:>+6.2f}  {r['scale']:>6.3f}  "
                  f"{r.get('anchor_rmse_px', float('nan')):>9.1f} px")
        else:
            print(f"{label:<22} ✗        {r.get('reason', r.get('exception', '?'))}")


if __name__ == "__main__":
    sys.exit(main())
