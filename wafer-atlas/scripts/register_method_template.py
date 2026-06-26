"""Method 2: register a sweep to atlas via template matching of atlas features.

Approach:
1. Extract small templates from the 0129 painted photo at known atlas
   locations (4D vertical bar, plus 2-3 other distinct features).
2. For each sweep, multi-scale template matching: try scales in a range
   covering 0.3× to 4× of the 0129 atlas scale. Use cv2.matchTemplate.
3. Each template's best (scale, position) match across the sweep gives
   ONE correspondence point: atlas-coord (cl, rl) at the template centre
   → sweep-pixel (x, y).
4. Solve affine (theta, x0, y0, scale) from 3+ correspondence points.

Notes:
- The 4D bar is unique within a die but the wafer has 4D-type dies at
  multiple (col, row) instances. Single-template match has a known
  phase-ambiguity (which die-instance was found). Resolved by using
  multiple template positions whose phases are DIFFERENT, then picking
  the assignment consistent across templates.
- Multi-scale: a small set of candidate scales {0.4, 0.6, 0.8, 1.0, 1.5,
  2.0, 3.0} covers the 0.385-2.0 M range we care about.
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


ATLAS_PATH = Path(__file__).parent.parent / "atlas.json"
GRID_0129_PATH = Path(__file__).parent.parent / "out" / "0129" / "grid_params.json"
PHOTO_0129_PATH = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-13/"
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S + 35mm extension/f_11/prev_step_0129_b.jpg"
)
OUT_DIR = Path(__file__).parent.parent / "out" / "registration"

# Candidate scales relative to the 0129 atlas size
SCALE_CANDIDATES = [0.35, 0.50, 0.65, 0.80, 1.00, 1.25, 1.50, 1.80, 2.10, 2.50, 3.00, 3.50]

# Downsample factor for the multi-scale search. Speeds up matchTemplate.
WORK_DS = 2


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


def _grid_xy(cl, rl, theta_rad, x0, y0, d_col, d_row):
    cos_t = np.cos(theta_rad)
    sin_t = np.sin(theta_rad)
    u = _cum(d_col, cl)
    v = _cum(d_row, rl)
    return (x0 + cos_t * u + sin_t * v,
            y0 + sin_t * u - cos_t * v)


def _die_uv_to_0129(col_label, row_label, u, v, params):
    """Map die-internal (col, row, u, v) → 0129-photo pixel coords."""
    cl = col_label + u
    rl = row_label + v
    return _grid_xy(cl, rl, params["theta_rad"], params["x0"], params["y0"],
                    params["d_col"], params["d_row"])


def extract_whole_die_template(grid_0129, gray_0129, col_label, row_label,
                                margin=0.05):
    """Extract a whole-die crop (with small margin) as a template."""
    # Die corners in 0129 coords
    u_lo, u_hi = -margin, 1 + margin
    v_lo, v_hi = -margin, 1 + margin
    pts = [
        _die_uv_to_0129(col_label, row_label, u_lo, v_lo, grid_0129),
        _die_uv_to_0129(col_label, row_label, u_lo, v_hi, grid_0129),
        _die_uv_to_0129(col_label, row_label, u_hi, v_lo, grid_0129),
        _die_uv_to_0129(col_label, row_label, u_hi, v_hi, grid_0129),
    ]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x_lo = max(0, int(min(xs)))
    x_hi = min(gray_0129.shape[1], int(max(xs)))
    y_lo = max(0, int(min(ys)))
    y_hi = min(gray_0129.shape[0], int(max(ys)))
    tpl = gray_0129[y_lo:y_hi, x_lo:x_hi].copy()
    return tpl, (col_label + 0.5, row_label + 0.5)


def extract_atlas_templates(atlas, grid_0129, gray_0129):
    """Build a list of whole-die templates at user-suggested distinctive types.

    User suggested 4B (3×3 grid), 2B (serpent + pads), 5C (3 horizontal pad
    bands; same type as 1C). Each whole-die template is more unique than
    cropped sub-features and gives a single best correspondence point.
    """
    templates = []

    candidates = [
        # (name, col_label, row_label, polarity_note)
        ("4B_die", 4, 1, "3×3 complex geometric shapes"),
        ("2B_die", 2, 1, "bond pads + middle serpent"),
        ("4C_die", 4, 2, "less-dense pad grid + 5+4 columns"),
    ]
    for (name, col_label, row_label, note) in candidates:
        tpl, (cl, rl) = extract_whole_die_template(grid_0129, gray_0129,
                                                    col_label, row_label)
        templates.append({
            "name": name,
            "image": tpl,
            "atlas_cl": cl,
            "atlas_rl": rl,
            "polarity": "mixed",
            "note": note,
        })
    return templates


def multi_scale_match(sweep_gray, template, scale_candidates,
                      work_ds=WORK_DS):
    """For each candidate scale, resize template and run cv2.matchTemplate.

    Returns the best (scale, score, x, y, all_peaks) tuple.
    `all_peaks` is a list of all peaks above 0.6 × best_score (for cluster analysis).
    """
    h0, w0 = template.shape
    H, W = sweep_gray.shape
    # Downsample sweep once
    sweep_ds = cv2.resize(sweep_gray, (W // work_ds, H // work_ds), interpolation=cv2.INTER_AREA)

    best = {"score": -np.inf}
    for s in scale_candidates:
        # Effective template size at this scale
        new_h = max(8, int(round(h0 * s / work_ds)))
        new_w = max(8, int(round(w0 * s / work_ds)))
        if new_h >= sweep_ds.shape[0] or new_w >= sweep_ds.shape[1]:
            continue
        tpl_r = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_AREA)
        # Match
        result = cv2.matchTemplate(sweep_ds.astype(np.float32),
                                    tpl_r.astype(np.float32),
                                    cv2.TM_CCOEFF_NORMED)
        max_score = float(result.max())
        if max_score > best["score"]:
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            # Position of template TOP-LEFT in sweep_ds → centre in full sweep
            cx_ds = max_loc[0] + new_w / 2
            cy_ds = max_loc[1] + new_h / 2
            cx = cx_ds * work_ds
            cy = cy_ds * work_ds
            best = {
                "score": max_score,
                "scale": s,
                "x": float(cx),
                "y": float(cy),
                "tpl_w_ds": new_w,
                "tpl_h_ds": new_h,
                "result_shape": result.shape,
            }
    return best


def fit_affine_from_correspondences(correspondences, atlas, theta_init_deg=4.5,
                                    scale_init=1.0):
    """Fit (theta, x0, y0, scale) given (atlas_cl, atlas_rl, sweep_x, sweep_y) tuples."""
    d_col = atlas["die_pitch_px_in_0129"]["d_col"]
    d_row = atlas["die_pitch_px_in_0129"]["d_row"]
    theta0 = np.radians(theta_init_deg)

    def residuals(p):
        theta, x0, y0, scale = p
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)
        out = []
        for (cl, rl, x_obs, y_obs) in correspondences:
            u = scale * _cum(d_col, cl)
            v = scale * _cum(d_row, rl)
            x_pred = x0 + cos_t * u + sin_t * v
            y_pred = y0 + sin_t * u - cos_t * v
            out.append(x_pred - x_obs)
            out.append(y_pred - y_obs)
        return np.array(out)

    # Seed from first correspondence
    cl0, rl0, x_seed, y_seed = correspondences[0]
    u_seed = scale_init * _cum(d_col, cl0)
    v_seed = scale_init * _cum(d_row, rl0)
    x0_init = x_seed - np.cos(theta0) * u_seed - np.sin(theta0) * v_seed
    y0_init = y_seed - np.sin(theta0) * u_seed + np.cos(theta0) * v_seed
    p0 = [theta0, x0_init, y0_init, scale_init]
    sol = least_squares(residuals, p0, method="lm")
    p = sol.x
    rmse = float(np.sqrt((sol.fun ** 2).mean()))
    return {
        "theta_rad": float(p[0]), "theta_deg": float(np.degrees(p[0])),
        "x0_img": float(p[1]), "y0_img": float(p[2]),
        "scale": float(p[3]), "rmse_px": rmse,
    }


def register_sweep_template(sweep_path, atlas, templates,
                            anchor_ground_truth=None, sweep_label="sweep"):
    """Run Method 2 (template matching) on one sweep."""
    sweep_rgb = np.asarray(Image.open(sweep_path).convert("RGB"), dtype=np.uint8)
    sweep_gray = cv2.cvtColor(sweep_rgb, cv2.COLOR_RGB2GRAY)
    print(f"  Sweep image: {sweep_gray.shape}")

    correspondences = []
    matches_log = []
    for tpl in templates:
        match = multi_scale_match(sweep_gray, tpl["image"], SCALE_CANDIDATES)
        matches_log.append({"name": tpl["name"], **match})
        print(f"  {tpl['name']}: score={match['score']:.3f}, "
              f"scale={match['scale']}, pos=({match['x']:.0f}, {match['y']:.0f})")
        if match["score"] > 0.30:
            correspondences.append((tpl["atlas_cl"], tpl["atlas_rl"],
                                     match["x"], match["y"]))

    if len(correspondences) < 3:
        return {"success": False, "reason": f"only {len(correspondences)} matches above threshold",
                "matches": matches_log}

    fit = fit_affine_from_correspondences(correspondences, atlas)
    result = {"success": True, "matches": matches_log,
              "correspondences": [list(c) for c in correspondences],
              **fit}

    # Validate against anchors
    if anchor_ground_truth:
        d_col = atlas["die_pitch_px_in_0129"]["d_col"]
        d_row = atlas["die_pitch_px_in_0129"]["d_row"]
        theta = fit["theta_rad"]
        cos_t, sin_t = np.cos(theta), np.sin(theta)
        errors = []
        for (cl, rl, x_obs, y_obs) in anchor_ground_truth:
            u = fit["scale"] * _cum(d_col, cl)
            v = fit["scale"] * _cum(d_row, rl)
            x_pred = fit["x0_img"] + cos_t * u + sin_t * v
            y_pred = fit["y0_img"] + sin_t * u - cos_t * v
            err = np.hypot(x_pred - x_obs, y_pred - y_obs)
            errors.append(err)
        result["anchor_errors_px"] = errors
        result["anchor_rmse_px"] = float(np.sqrt(np.mean(np.array(errors) ** 2)))
        print(f"  Anchor RMSE: {result['anchor_rmse_px']:.1f} px (errors: {[f'{e:.0f}' for e in errors]})")

    return result


def main():
    atlas = json.load(open(ATLAS_PATH))
    grid_0129 = json.load(open(GRID_0129_PATH))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Extracting templates from 0129 ===")
    gray_0129 = cv2.cvtColor(
        np.asarray(Image.open(PHOTO_0129_PATH).convert("RGB"), dtype=np.uint8),
        cv2.COLOR_RGB2GRAY)
    templates = extract_atlas_templates(atlas, grid_0129, gray_0129)
    for tpl in templates:
        print(f"  {tpl['name']}: shape {tpl['image'].shape}, "
              f"atlas (cl, rl) = ({tpl['atlas_cl']:.2f}, {tpl['atlas_rl']:.2f})")
        # Save the template for inspection
        Image.fromarray(tpl["image"]).save(OUT_DIR / f"template_{tpl['name']}.png")

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
        result = register_sweep_template(sweep_path, atlas, templates,
                                          anchor_ground_truth=anchors,
                                          sweep_label=sweep_label)
        all_results[sweep_label] = result

    out_json = OUT_DIR / "method_template_results.json"
    with open(out_json, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved: {out_json}")

    # Summary
    print("\n=== Method 2 (template) summary ===")
    print(f"{'sweep':<22} {'success':<8} {'theta°':<8} {'scale':<8} {'anchor_RMSE':<12}")
    for label, r in all_results.items():
        if r.get("success"):
            print(f"{label:<22} ✓        {r['theta_deg']:>+6.2f}  {r['scale']:>6.3f}  "
                  f"{r.get('anchor_rmse_px', float('nan')):>9.1f} px")
        else:
            print(f"{label:<22} ✗        {r.get('reason', 'unknown')}")


if __name__ == "__main__":
    sys.exit(main())
