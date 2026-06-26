"""Method 3 — register a sweep to atlas via scribe-grid detection.

Pipeline:
  1. Load sweep image; build silicon mask (chroma filter); crop to bbox.
  2. Estimate wafer rotation (Hough on Canny edges).
  3. De-rotate. Compute column- and row-projection profiles within silicon mask.
  4. FFT each profile to find dominant pitch (the AVERAGE die pitch).
  5. Detect individual scribe positions via projection-profile minima.
  6. Match the detected spacing pattern to the atlas's super-cell signature
     (one wide col every 4; one tall row every 4) — pick the phase
     (col_phase in 0..3, row_phase in 0..3) that best fits the data.
  7. Solve for (theta, x0, y0, scale) by least squares against the
     (cl, rl) ↔ (x, y) pairs.

Output: registration params + RMSE against any user-supplied anchors.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.ndimage import binary_opening, gaussian_filter
from scipy.optimize import least_squares
from scipy.signal import find_peaks
from skimage.feature import canny
from skimage.transform import probabilistic_hough_line, rotate


ATLAS_PATH = Path(__file__).parent.parent / "atlas.json"
OUT_DIR = Path(__file__).parent.parent / "out" / "registration"

DS = 4  # downsample factor for FFT / Hough work


def _silicon_mask(rgb):
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    gray = 0.299 * R + 0.587 * G + 0.114 * B
    chroma_green = G - 0.5 * (R + B)
    sat = rgb.max(-1) - rgb.min(-1)
    mask = (
        (chroma_green < 5.0)
        & (gray > 60.0)
        & ~((gray > 180.0) & (sat < 30.0))
    )
    return binary_opening(mask, iterations=3)


def _bbox(mask):
    ys, xs = np.where(mask)
    return ys.min(), ys.max(), xs.min(), xs.max()


def _downsample(arr, k):
    h, w = arr.shape[:2]
    hd, wd = h // k, w // k
    arr = arr[:hd * k, :wd * k]
    if arr.ndim == 2:
        return arr.reshape(hd, k, wd, k).mean(axis=(1, 3))
    return arr.reshape(hd, k, wd, k, -1).mean(axis=(1, 3))


def _estimate_rotation(gray_ds, mask_ds):
    """Hough-based rotation estimate. Returns rotation in degrees (CW positive)."""
    g = gray_ds.copy()
    g[~mask_ds] = g[mask_ds].mean()
    edges = canny(g / 255.0, sigma=1.0, low_threshold=0.05, high_threshold=0.15)
    edges &= mask_ds
    raw_lines = probabilistic_hough_line(edges, threshold=20, line_length=30, line_gap=12)
    if not raw_lines:
        return 0.0
    angs, lens = [], []
    for (x0, y0), (x1, y1) in raw_lines:
        a = float(np.degrees(np.arctan2(y1 - y0, x1 - x0)) % 180.0)
        L = float(np.hypot(x1 - x0, y1 - y0))
        angs.append(a)
        lens.append(L)
    angs = np.asarray(angs)
    lens = np.asarray(lens)
    # Weighted hue histogram
    BIN = 1.0
    n = int(180 / BIN)
    hist = np.zeros(n)
    for a, L in zip(angs, lens):
        hist[int(a / BIN) % n] += L
    hist = gaussian_filter(hist, sigma=1.0, mode="wrap")
    # Dominant peak — close to 0 or 90 → that's the rotation
    primary_bin = int(hist.argmax())
    primary_ang = (primary_bin + 0.5) * BIN
    # Wrap to [-45, 45) relative to nearest cardinal direction
    if primary_ang > 135:
        rot = primary_ang - 180
    elif primary_ang > 45:
        rot = primary_ang - 90
    else:
        rot = primary_ang
    return rot


def _profile_minima(profile, min_distance_ds=15, n_min_required=5):
    """Find ALL scribe minima with small min_distance, then filter by modal spacing.

    Strategy:
      1. Detect candidate minima with `min_distance_ds` (small) → over-detect.
      2. Compute spacings between consecutive minima.
      3. Find the modal/median spacing (= die pitch).
      4. Filter minima: drop those whose spacing to prev/next is < 0.5 × modal
         (these are sub-die features that crept in).
    """
    smoothed = gaussian_filter(profile - gaussian_filter(profile, sigma=80, mode="nearest"),
                                sigma=2.5)
    peaks, props = find_peaks(-smoothed, distance=min_distance_ds, prominence=1.0)
    if len(peaks) < n_min_required:
        peaks, props = find_peaks(-smoothed, distance=min_distance_ds, prominence=0.3)
    if len(peaks) < n_min_required:
        return peaks.tolist(), smoothed, None
    spacings = np.diff(peaks)
    # Modal spacing: use the median as the "die pitch" estimate
    pitch_estimate = float(np.median(spacings))
    # Filter: keep peaks whose neighbour spacings are within [0.7, 1.5] × pitch
    keep = [True] * len(peaks)
    for i in range(len(peaks)):
        left_ok = (i == 0) or (peaks[i] - peaks[i - 1] >= 0.7 * pitch_estimate)
        right_ok = (i == len(peaks) - 1) or (peaks[i + 1] - peaks[i] >= 0.7 * pitch_estimate)
        if not (left_ok and right_ok):
            keep[i] = False
    cleaned = [int(p) for p, k in zip(peaks, keep) if k]
    return cleaned, smoothed, pitch_estimate


def _fft_dominant_pitch(profile, min_pitch=20, max_pitch=300):
    p = profile - gaussian_filter(profile, sigma=80, mode="nearest")
    p = p * np.hanning(len(p))
    F = np.fft.rfft(p)
    freqs = np.fft.rfftfreq(len(p), d=1.0)
    mag = np.abs(F)
    f_min, f_max = 1.0 / max_pitch, 1.0 / min_pitch
    band = (freqs >= f_min) & (freqs <= f_max)
    if not band.any():
        return None
    idx = np.where(band)[0]
    best = idx[mag[idx].argmax()]
    return 1.0 / freqs[best] if freqs[best] > 0 else None


def _match_supercell_phase(positions, atlas_pitch_pattern):
    """Match an observed sequence of scribe positions to atlas super-cell.

    Args:
      positions: list of detected scribe pixel positions (sorted ascending)
      atlas_pitch_pattern: 4-tuple of relative pitches, e.g. (542, 458, 454, 453)
                           where one entry is the "wide" one.

    Returns:
      dict with best phase (which atlas col-type the first position is),
      pixel-per-atlas-unit scale, and per-position assigned col-line indices.
    """
    if len(positions) < 5:
        return None
    positions = np.asarray(positions)
    spacings = np.diff(positions)  # n-1 spacings for n positions
    n_spacings = len(spacings)
    atlas_array = np.array(atlas_pitch_pattern, dtype=np.float64)

    best = None
    for phase in range(4):
        # phase = which atlas col-type the FIRST detected position is (=col_line mod 4)
        # So the i-th spacing is from atlas col-type ((phase + i) mod 4)
        expected = np.array([atlas_array[(phase + i) % 4] for i in range(n_spacings)])
        # Fit a single scale by least-squares: spacings ≈ scale * expected
        scale = float((spacings * expected).sum() / (expected ** 2).sum())
        residuals = spacings - scale * expected
        rmse = float(np.sqrt((residuals ** 2).mean()))
        if best is None or rmse < best["rmse"]:
            best = {
                "phase": phase,
                "scale": scale,
                "rmse": rmse,
                "positions": positions.tolist(),
                "assigned_col_lines": [phase + i for i in range(len(positions))],
            }
    return best


def register_sweep(image_path, atlas, anchors=None):
    """Run Method 3 registration on a sweep image. Returns dict with params + diagnostics."""
    rgb = np.asarray(Image.open(image_path).convert("RGB"), dtype=np.float32)
    H, W = rgb.shape[:2]
    print(f"Loaded {image_path}: {H}×{W}")

    mask = _silicon_mask(rgb)
    print(f"Silicon mask area: {mask.sum()} px ({100 * mask.mean():.1f}%)")
    y0, y1, x0, x1 = _bbox(mask)
    print(f"Silicon bbox: y={y0}..{y1} x={x0}..{x1}")

    rgb_crop = rgb[y0:y1, x0:x1]
    mask_crop = mask[y0:y1, x0:x1]
    rgb_ds = _downsample(rgb_crop, DS)
    mask_ds = _downsample(mask_crop.astype(np.float32), DS) > 0.5
    gray_ds = (0.299 * rgb_ds[..., 0] + 0.587 * rgb_ds[..., 1]
               + 0.114 * rgb_ds[..., 2]).astype(np.float32)
    print(f"DS shape: {gray_ds.shape}")

    # Estimate rotation
    rot_deg = _estimate_rotation(gray_ds, mask_ds)
    print(f"Estimated rotation (Hough): {rot_deg:+.3f}°")
    gray_rot = rotate(gray_ds, rot_deg, resize=False, preserve_range=True,
                      mode="constant", cval=gray_ds[mask_ds].mean())
    mask_rot = rotate(mask_ds.astype(np.float32), rot_deg, resize=False,
                      preserve_range=True, order=0) > 0.5

    # Projection profiles (only over silicon-masked rows/cols)
    col_sum = np.where(mask_rot, gray_rot, 0).sum(axis=0)
    col_cnt = mask_rot.sum(axis=0)
    col_profile = np.where(col_cnt >= 50, col_sum / np.maximum(col_cnt, 1), np.nan)
    row_sum = np.where(mask_rot, gray_rot, 0).sum(axis=1)
    row_cnt = mask_rot.sum(axis=1)
    row_profile = np.where(row_cnt >= 50, row_sum / np.maximum(row_cnt, 1), np.nan)
    c_valid = np.where(~np.isnan(col_profile))[0]
    r_valid = np.where(~np.isnan(row_profile))[0]
    cm = col_profile[c_valid[0]:c_valid[-1] + 1]
    rm = row_profile[r_valid[0]:r_valid[-1] + 1]
    cm = np.where(np.isnan(cm), np.nanmean(cm), cm)
    rm = np.where(np.isnan(rm), np.nanmean(rm), rm)

    # FFT dominant pitch (in ds-px) as a guess for pitch
    fft_col_pitch = _fft_dominant_pitch(cm, min_pitch=20, max_pitch=300)
    fft_row_pitch = _fft_dominant_pitch(rm, min_pitch=20, max_pitch=300)
    print(f"FFT dominant pitch: cols={fft_col_pitch:.1f} ds-px, rows={fft_row_pitch:.1f} ds-px")

    # Detect scribe positions — use small min_distance, then filter by modal spacing
    col_peaks, _, col_pitch_est = _profile_minima(cm, min_distance_ds=15)
    row_peaks, _, row_pitch_est = _profile_minima(rm, min_distance_ds=15)
    print(f"Detected scribes: {len(col_peaks)} columns (modal pitch {col_pitch_est}), "
          f"{len(row_peaks)} rows (modal pitch {row_pitch_est})")

    # Match super-cell phase
    atlas_d_col = atlas["die_pitch_px_in_0129"]["d_col"]
    atlas_d_row = atlas["die_pitch_px_in_0129"]["d_row"]
    col_match = _match_supercell_phase(col_peaks, atlas_d_col)
    row_match = _match_supercell_phase(row_peaks, atlas_d_row)
    if col_match:
        print(f"Col super-cell phase: {col_match['phase']}, "
              f"scale: {col_match['scale']:.4f} (ds-px/atlas-unit), "
              f"RMSE: {col_match['rmse']:.2f} ds-px")
    if row_match:
        print(f"Row super-cell phase: {row_match['phase']}, "
              f"scale: {row_match['scale']:.4f}, RMSE: {row_match['rmse']:.2f}")

    # Build (cl_line, rl_line, x_image, y_image) correspondence pairs.
    # For each detected col scribe at (col_x_ds, any row), we know cl_line =
    # col_match['phase'] + i. Same for rows.
    # Convert from rotated-ds-px back to original image coords:
    #   1. Un-downsample (multiply by DS) → rotated full-res-px
    #   2. Add (x0, y0) bbox offset before rotation? Wait, we rotated AFTER
    #      bbox cropping. The bbox crop's centre is at original (x0 + W_crop/2, y0 + H_crop/2)
    #      but rotation is in cropped frame.
    # Simpler: build all (image_x, image_y, cl_line, rl_line) pairs as
    # cross-products of (col scribe × row scribe), then fit a single affine.

    if col_match is None or row_match is None:
        return {"success": False, "reason": "super-cell phase match failed"}

    pairs = []  # (cl_line, rl_line, x_orig, y_orig)
    for ci, c_pos_ds in enumerate(col_peaks):
        for ri, r_pos_ds in enumerate(row_peaks):
            cl = col_match["phase"] + ci
            rl = row_match["phase"] + ri
            # Position in rotated-cropped-ds frame:
            x_rot_ds = c_valid[0] + c_pos_ds
            y_rot_ds = r_valid[0] + r_pos_ds
            # Un-rotate inside the cropped frame
            cx_ds, cy_ds = gray_ds.shape[1] / 2, gray_ds.shape[0] / 2
            dx, dy = x_rot_ds - cx_ds, y_rot_ds - cy_ds
            cos_r, sin_r = np.cos(np.radians(rot_deg)), np.sin(np.radians(rot_deg))
            x_orig_crop_ds = cos_r * dx - sin_r * dy + cx_ds
            y_orig_crop_ds = sin_r * dx + cos_r * dy + cy_ds
            # Un-downsample, then un-crop
            x_orig = x_orig_crop_ds * DS + x0
            y_orig = y_orig_crop_ds * DS + y0
            pairs.append((cl, rl, x_orig, y_orig))

    print(f"Generated {len(pairs)} (cl, rl, x, y) correspondence pairs")

    # Fit the affine: (cl, rl) → (x, y) using the atlas pitches
    # Model: x = x0_img + cos(theta) * (scale × cum_col(cl)) + sin(theta) * (scale × cum_row(rl))
    #        y = y0_img + sin(theta) * (scale × cum_col(cl)) - cos(theta) * (scale × cum_row(rl))
    def _cum(d4, k):
        if k <= 0: return 0.0
        ki = int(np.floor(k))
        frac = k - ki
        full = ki // 4
        rem = ki % 4
        c = full * sum(d4) + sum(d4[:rem])
        if frac > 0:
            c += frac * d4[rem]
        return c

    def residuals(p, pairs):
        theta, x0_img, y0_img, scale = p
        cos_t, sin_t = np.cos(theta), np.sin(theta)
        out = []
        for (cl, rl, x_obs, y_obs) in pairs:
            u = scale * _cum(atlas_d_col, cl)
            v = scale * _cum(atlas_d_row, rl)
            x_pred = x0_img + cos_t * u + sin_t * v
            y_pred = y0_img + sin_t * u - cos_t * v
            out.append(x_pred - x_obs)
            out.append(y_pred - y_obs)
        return np.array(out)

    # Initial guess
    rot_rad_init = np.radians(rot_deg)
    scale_init = col_match["scale"] * DS / atlas_d_col[col_match["phase"]]  # very rough
    # Use first pair to seed x0, y0
    cl0, rl0, x_seed, y_seed = pairs[0]
    u_seed = scale_init * _cum(atlas_d_col, cl0)
    v_seed = scale_init * _cum(atlas_d_row, rl0)
    x0_init = x_seed - np.cos(rot_rad_init) * u_seed - np.sin(rot_rad_init) * v_seed
    y0_init = y_seed - np.sin(rot_rad_init) * u_seed + np.cos(rot_rad_init) * v_seed
    p0 = [rot_rad_init, x0_init, y0_init, scale_init]

    sol = least_squares(residuals, p0, args=(pairs,), method="lm")
    p = sol.x
    rmse = float(np.sqrt((sol.fun ** 2).mean()))
    result = {
        "success": True,
        "theta_rad": float(p[0]),
        "theta_deg": float(np.degrees(p[0])),
        "x0_img": float(p[1]),
        "y0_img": float(p[2]),
        "scale": float(p[3]),
        "fit_rmse_px": rmse,
        "n_pairs": len(pairs),
        "col_phase": col_match["phase"],
        "row_phase": row_match["phase"],
        "col_match_rmse_ds_px": col_match["rmse"],
        "row_match_rmse_ds_px": row_match["rmse"],
    }
    print(f"\nFit RMSE: {rmse:.2f} px over {len(pairs)} pairs")
    print(f"  theta: {result['theta_deg']:+.3f}° CW")
    print(f"  origin: ({result['x0_img']:.1f}, {result['y0_img']:.1f})")
    print(f"  scale: {result['scale']:.4f}× of atlas (0129) pitches")
    print(f"  col_phase: {result['col_phase']} (atlas col-line index of first detected scribe)")
    print(f"  row_phase: {result['row_phase']}")

    # Validate against user anchors if provided
    if anchors:
        print(f"\nValidation against {len(anchors)} user anchors:")
        theta = result["theta_rad"]
        cos_t, sin_t = np.cos(theta), np.sin(theta)
        anchor_errors = []
        for (cl, rl, x_obs, y_obs) in anchors:
            u = result["scale"] * _cum(atlas_d_col, cl)
            v = result["scale"] * _cum(atlas_d_row, rl)
            x_pred = result["x0_img"] + cos_t * u + sin_t * v
            y_pred = result["y0_img"] + sin_t * u - cos_t * v
            err = np.hypot(x_pred - x_obs, y_pred - y_obs)
            anchor_errors.append(err)
            print(f"  (cl={cl}, rl={rl}) given ({x_obs}, {y_obs}) → pred ({x_pred:.1f}, {y_pred:.1f}) err={err:.2f} px")
        result["anchor_rmse_px"] = float(np.sqrt(np.mean(np.array(anchor_errors) ** 2)))
        print(f"  Anchor RMSE: {result['anchor_rmse_px']:.2f} px")

    return result


def main():
    atlas = json.load(open(ATLAS_PATH))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Sweep 1: 100-400 @ 1:2.60 F11
    sweep1_path = ("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
                   "NIKKOR Z 100-400mm f_4.5-5.6 VR S/1_2.60/F11/"
                   "00296|NIKKOR Z 100-400mm f_4.5-5.6 VR S|1_2.60|400.0 mm|F11|"
                   "alm-20260208-221844-296.jpg")
    sweep1_anchors = [
        (1, 1, 1827, 3548),
        (10, 1, 6078, 3901),
        (6, 5, 4341, 1853),
    ]
    print("=" * 70)
    print("SWEEP 1: 100-400 @ M=0.385 F11 (Task 2)")
    print("=" * 70)
    result1 = register_sweep(sweep1_path, atlas, sweep1_anchors)
    json.dump(result1, open(OUT_DIR / "sweep1_method3.json", "w"), indent=2)


if __name__ == "__main__":
    sys.exit(main())
