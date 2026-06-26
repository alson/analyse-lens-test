"""Extract top-3 die-type crops + run feature CV.

Top-3 (user-prioritised 2026-05-18):
  1. 4D — vertical bar at (u 0.3–0.35, v 0.4–0.6)  [slanted-edge target]
  2. 3E — three horizontal pad bands across entire die
  3. 3C — three pad columns (u 0–1, v 0–0.7) + irregular right strip (u 0.7–1, v 0–1)

For each die-type we:
  1. Extract a margin-padded de-rotated crop using the super-cell grid params.
  2. Run feature-type-specific CV (line detection / projection + connected
     components / 2D-FFT for pad pitch).
  3. Save a per-die annotation PNG + an atlas YAML entry.

User's coordinate convention:
  (u, v) ∈ [0, 1]², (0, 0) = die bottom-left, (1, 1) = top-right.

Grid params from grid_supercell_refined.py:
  θ = 4.665° CW, origin (1063.9, 4028.6),
  d_col = [539.02, 457.54, 453.95, 453.24] (type 0 WIDE),
  d_row = [455.88, 543.88, 452.83, 452.19] (type 1 TALL).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.signal import find_peaks


PHOTO_PATH = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-13/"
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S/f_8/step_0131_c.jpg"
)
OUT_DIR = Path(__file__).parent.parent / "out"

THETA_RAD = np.radians(4.665)
GRID_X0, GRID_Y0 = 1063.9, 4028.6
D_COL = np.array([539.02, 457.54, 453.95, 453.24])
D_ROW = np.array([455.88, 543.88, 452.83, 452.19])

# Output crop size
OUT_SIZE = 600  # px; gives sub-px resolution since die ~470 px
MARGIN = 0.05   # 5% margin around the die


def _cum(d4: np.ndarray, k: float) -> float:
    if k <= 0:
        return 0.0
    k_int = int(np.floor(k))
    frac = k - k_int
    full = k_int // 4
    rem = k_int % 4
    c = full * d4.sum() + d4[:rem].sum()
    if frac > 0:
        c += frac * d4[rem]
    return c


def extract_die_crop(image: np.ndarray, cl_label: int, rl_label: int,
                     out_size: int = OUT_SIZE,
                     margin: float = MARGIN) -> np.ndarray:
    """Return a de-rotated out_size × out_size die crop in wafer-native orientation.

    Output row 0 = die top (v=1+margin), row -1 = die bottom (v=-margin).
    Output col 0 = die left (u=-margin), col -1 = die right (u=1+margin).
    """
    cos_t = np.cos(THETA_RAD)
    sin_t = np.sin(THETA_RAD)
    base_u = _cum(D_COL, cl_label)
    base_v = _cum(D_ROW, rl_label)
    du = D_COL[cl_label % 4]
    dv = D_ROW[rl_label % 4]
    u_range = np.linspace(-margin, 1 + margin, out_size)
    v_range = np.linspace(1 + margin, -margin, out_size)
    U, V = np.meshgrid(u_range, v_range)
    u_cum = base_u + U * du
    v_cum = base_v + V * dv
    x_image = GRID_X0 + cos_t * u_cum + sin_t * v_cum
    y_image = GRID_Y0 + sin_t * u_cum - cos_t * v_cum
    coords = np.stack([y_image.ravel(), x_image.ravel()])
    sampled = map_coordinates(image, coords, order=1, mode="nearest")
    return sampled.reshape(out_size, out_size).astype(np.float32)


def uv_to_pixel(u: float, v: float, out_size: int = OUT_SIZE,
                margin: float = MARGIN) -> tuple[int, int]:
    """Die (u, v) → output crop (col_pix, row_pix)."""
    col_pix = int(round((u + margin) / (1 + 2 * margin) * (out_size - 1)))
    row_pix = int(round((1 + margin - v) / (1 + 2 * margin) * (out_size - 1)))
    return col_pix, row_pix


def pixel_to_uv(col_pix: int, row_pix: int, out_size: int = OUT_SIZE,
                margin: float = MARGIN) -> tuple[float, float]:
    """Output (col_pix, row_pix) → die (u, v)."""
    u = col_pix / (out_size - 1) * (1 + 2 * margin) - margin
    v = 1 + margin - row_pix / (out_size - 1) * (1 + 2 * margin)
    return u, v


# --- Feature-specific CV --------------------------------------------------

def find_vertical_bar(crop: np.ndarray,
                     hint_u: tuple[float, float] = (0.25, 0.40),
                     hint_v: tuple[float, float] = (0.35, 0.65)
                     ) -> dict:
    """Locate a strong vertical bar inside the user's hint region.

    Strategy: within the hint region, compute mean intensity per column.
    The bar appears as a peak or trough; pick whichever is more extreme.
    Width = FWHM of the peak/trough. Then within the bar's column range,
    compute mean per row to find the bar's vertical extent (where it's
    most distinct from the background).
    """
    u_lo, u_hi = hint_u
    v_lo, v_hi = hint_v
    c0, r1 = uv_to_pixel(u_lo, v_lo)
    c1, r0 = uv_to_pixel(u_hi, v_hi)
    # r0 < r1 in row-pixel coords (v=v_hi is the top → smaller row_pix)
    patch = crop[r0:r1, c0:c1]
    col_mean = patch.mean(axis=0)
    bg = float(np.median(crop[r0:r1, max(0, c0 - 40):c0]))  # left of hint
    if bg == 0:
        bg = float(crop[r0:r1, c0:c1].mean())
    # The bar could be bright or dark relative to bg. Pick larger excursion.
    bright_dev = col_mean.max() - bg
    dark_dev = bg - col_mean.min()
    polarity = "bright" if bright_dev >= dark_dev else "dark"
    if polarity == "bright":
        bar_idx = int(np.argmax(col_mean))
        thresh = bg + 0.5 * (col_mean[bar_idx] - bg)
        in_bar = col_mean > thresh
    else:
        bar_idx = int(np.argmin(col_mean))
        thresh = bg - 0.5 * (bg - col_mean[bar_idx])
        in_bar = col_mean < thresh
    bar_cols = np.where(in_bar)[0]
    if len(bar_cols) == 0:
        return {"found": False, "polarity": polarity, "col_mean": col_mean.tolist()}
    bar_c_lo = c0 + int(bar_cols.min())
    bar_c_hi = c0 + int(bar_cols.max())
    # Now find vertical extent: scan rows in the bar's column range
    bar_strip = crop[:, bar_c_lo:bar_c_hi + 1]
    row_mean = bar_strip.mean(axis=1)
    # Background near top + bottom edges of the crop
    edge_bg = float(np.median(np.concatenate([row_mean[:30], row_mean[-30:]])))
    if polarity == "bright":
        thresh_r = edge_bg + 0.5 * (row_mean.max() - edge_bg)
        in_row = row_mean > thresh_r
    else:
        thresh_r = edge_bg - 0.5 * (edge_bg - row_mean.min())
        in_row = row_mean < thresh_r
    rows_in = np.where(in_row)[0]
    if len(rows_in) == 0:
        return {"found": False, "polarity": polarity}
    # Take the longest contiguous run intersecting the hint v range
    bar_r_lo = int(rows_in.min())
    bar_r_hi = int(rows_in.max())
    u_min, v_max = pixel_to_uv(bar_c_lo, bar_r_lo)
    u_max, v_min = pixel_to_uv(bar_c_hi, bar_r_hi)
    return {
        "found": True,
        "polarity": polarity,
        "bbox_uv": [round(u_min, 3), round(v_min, 3),
                    round(u_max, 3), round(v_max, 3)],
        "bbox_px": [bar_c_lo, bar_r_lo, bar_c_hi, bar_r_hi],
        "edge_sharpness_lr": _edge_sharpness(crop, bar_c_lo, bar_r_lo, bar_r_hi),
        "edge_sharpness_rt": _edge_sharpness(crop, bar_c_hi, bar_r_lo, bar_r_hi),
    }


def _edge_sharpness(crop: np.ndarray, col: int, r0: int, r1: int) -> float:
    """RMS gradient |dI/du| across a vertical edge — a 1-px-wide measure."""
    if col < 2 or col >= crop.shape[1] - 2:
        return 0.0
    strip = crop[r0:r1, col - 2:col + 3]
    return float(np.abs(np.diff(strip, axis=1)).mean())


def find_horizontal_pad_bands(crop: np.ndarray, n_bands: int = 3) -> dict:
    """Find n_bands horizontal pad-pad bands.

    Strategy: row-projection profile; the bands are intensity-elevated
    relative to the gaps. Detrend, smooth, find top-n peaks.
    """
    H = crop.shape[0]
    row_mean = crop.mean(axis=1)
    # Detrend with a wide gaussian
    trend = gaussian_filter(row_mean, sigma=60, mode="nearest")
    detrended = row_mean - trend
    smoothed = gaussian_filter(detrended, sigma=3.0)
    peaks, props = find_peaks(smoothed, distance=H // (n_bands * 2),
                              prominence=1.0)
    # Keep top n_bands by prominence
    if len(peaks) < n_bands:
        # try with darker (bands are dark): invert
        peaks_d, props_d = find_peaks(-smoothed, distance=H // (n_bands * 2),
                                       prominence=1.0)
        if len(peaks_d) > len(peaks):
            peaks, props = peaks_d, props_d
            smoothed = -smoothed
    if len(peaks) >= n_bands:
        order = np.argsort(-props["prominences"])
        keep = sorted(peaks[order[:n_bands]].tolist())
        peaks = np.array(keep)
    # For each band centre, find FWHM width
    bands = []
    for p in peaks:
        amp = smoothed[p]
        bg = np.median(smoothed)
        half = (amp + bg) / 2
        # Walk outward from p
        r0 = p
        while r0 > 0 and smoothed[r0] > half:
            r0 -= 1
        r1 = p
        while r1 < len(smoothed) - 1 and smoothed[r1] > half:
            r1 += 1
        # In u-v: band spans full u (0..1)
        _, v_top = pixel_to_uv(0, r0)
        _, v_bot = pixel_to_uv(0, r1)
        u_min, _ = pixel_to_uv(0, p)
        u_max, _ = pixel_to_uv(OUT_SIZE - 1, p)
        # pad pitch via 2D FFT inside the band
        band_strip = crop[r0:r1 + 1, :]
        pitch_info = _pad_pitch(band_strip) if band_strip.shape[0] >= 16 else None
        bands.append({
            "centre_v": round((v_top + v_bot) / 2, 3),
            "bbox_uv": [round(u_min, 3), round(v_bot, 3),
                        round(u_max, 3), round(v_top, 3)],
            "bbox_px": [0, r0, OUT_SIZE - 1, r1],
            "pad_pitch": pitch_info,
        })
    bands.sort(key=lambda b: -b["centre_v"])  # top band first
    return {"found": len(bands) > 0, "n_bands_detected": len(bands), "bands": bands}


def _pad_pitch(band_strip: np.ndarray) -> dict | None:
    """2D FFT of a pad-band strip → fundamental pitch in u and v."""
    H, W = band_strip.shape
    if H < 8 or W < 8:
        return None
    s = band_strip - band_strip.mean()
    han = np.outer(np.hanning(H), np.hanning(W)).astype(np.float32)
    s = s * han
    F = np.fft.fftshift(np.fft.fft2(s))
    mag = np.abs(F)
    cy, cx = H // 2, W // 2
    r = np.sqrt(np.add.outer((np.arange(H) - cy) ** 2,
                              (np.arange(W) - cx) ** 2))
    mag[r < 3] = 0
    # Find peaks along each axis
    # u-axis fundamental (horizontal periodicity → spike along x in FFT)
    u_profile = mag[cy, cx + 3:cx + W // 2]
    if u_profile.max() > 0:
        u_peak = int(np.argmax(u_profile)) + 3
        pitch_u_px = W / u_peak if u_peak else None
    else:
        pitch_u_px = None
    v_profile = mag[cy + 3:cy + H // 2, cx]
    if v_profile.max() > 0:
        v_peak = int(np.argmax(v_profile)) + 3
        pitch_v_px = H / v_peak if v_peak else None
    else:
        pitch_v_px = None
    return {
        "pitch_u_px": round(pitch_u_px, 2) if pitch_u_px else None,
        "pitch_v_px": round(pitch_v_px, 2) if pitch_v_px else None,
    }


def find_pad_columns(crop: np.ndarray, n_cols: int = 3,
                     u_range: tuple[float, float] = (0.0, 1.0),
                     v_range: tuple[float, float] = (0.0, 0.7)) -> dict:
    """Find n_cols pad columns within the user's bbox.

    Mirror of find_horizontal_pad_bands but along the column axis.
    """
    c0, r_v_hi = uv_to_pixel(u_range[0], v_range[1])
    c1, r_v_lo = uv_to_pixel(u_range[1], v_range[0])
    patch = crop[r_v_hi:r_v_lo, c0:c1]
    col_mean = patch.mean(axis=0)
    trend = gaussian_filter(col_mean, sigma=60, mode="nearest")
    detrended = col_mean - trend
    smoothed = gaussian_filter(detrended, sigma=3.0)
    peaks, props = find_peaks(smoothed, distance=patch.shape[1] // (n_cols * 2),
                              prominence=1.0)
    if len(peaks) < n_cols:
        peaks_d, props_d = find_peaks(-smoothed, distance=patch.shape[1] // (n_cols * 2),
                                       prominence=1.0)
        if len(peaks_d) > len(peaks):
            peaks, props = peaks_d, props_d
            smoothed = -smoothed
    if len(peaks) >= n_cols:
        order = np.argsort(-props["prominences"])
        keep = sorted(peaks[order[:n_cols]].tolist())
        peaks = np.array(keep)
    columns = []
    for p in peaks:
        amp = smoothed[p]
        bg = np.median(smoothed)
        half = (amp + bg) / 2
        c_lo = p
        while c_lo > 0 and smoothed[c_lo] > half:
            c_lo -= 1
        c_hi = p
        while c_hi < len(smoothed) - 1 and smoothed[c_hi] > half:
            c_hi += 1
        u_lo, _ = pixel_to_uv(c0 + c_lo, 0)
        u_hi, _ = pixel_to_uv(c0 + c_hi, 0)
        col_strip = patch[:, c_lo:c_hi + 1]
        pitch_info = _pad_pitch(col_strip) if col_strip.shape[1] >= 16 else None
        columns.append({
            "centre_u": round((u_lo + u_hi) / 2, 3),
            "bbox_uv": [round(u_lo, 3), round(v_range[0], 3),
                        round(u_hi, 3), round(v_range[1], 3)],
            "bbox_px": [c0 + c_lo, r_v_hi, c0 + c_hi, r_v_lo],
            "pad_pitch": pitch_info,
        })
    columns.sort(key=lambda c: c["centre_u"])
    return {"found": len(columns) > 0, "n_columns_detected": len(columns), "columns": columns}


# --- Visualisation --------------------------------------------------------

def _draw_bbox_uv(ax, bbox_uv, **kw):
    u_min, v_min, u_max, v_max = bbox_uv
    c_lo, r_hi = uv_to_pixel(u_min, v_min)
    c_hi, r_lo = uv_to_pixel(u_max, v_max)
    ax.add_patch(plt.Rectangle((c_lo, r_lo), c_hi - c_lo, r_hi - r_lo,
                                fill=False, **kw))


def save_die_overlay(crop: np.ndarray, label: str,
                     features: dict, out_path: Path, description: str):
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.imshow(crop, cmap="gray")
    # uv grid lines at 0.2 intervals
    for u in np.arange(0.0, 1.001, 0.2):
        cp, _ = uv_to_pixel(u, 0.5)
        ax.axvline(cp, color="cyan", lw=0.3, alpha=0.4)
        ax.text(cp, OUT_SIZE - 5, f"{u:.1f}", color="cyan", fontsize=7,
                ha="center", va="top")
    for v in np.arange(0.0, 1.001, 0.2):
        _, rp = uv_to_pixel(0.5, v)
        ax.axhline(rp, color="cyan", lw=0.3, alpha=0.4)
        ax.text(5, rp, f"{v:.1f}", color="cyan", fontsize=7,
                ha="left", va="center")
    if "bar" in features and features["bar"].get("found"):
        bar = features["bar"]
        _draw_bbox_uv(ax, bar["bbox_uv"], edgecolor="yellow", lw=2)
        u_min, v_min, u_max, v_max = bar["bbox_uv"]
        ax.text(uv_to_pixel(u_min, v_max)[0],
                uv_to_pixel(u_min, v_max)[1] - 6,
                f"bar {bar['polarity']} "
                f"({u_min:.2f},{v_min:.2f})-({u_max:.2f},{v_max:.2f})",
                color="yellow", fontsize=8, va="bottom")
    if "bands" in features and features["bands"].get("found"):
        for i, b in enumerate(features["bands"]["bands"]):
            _draw_bbox_uv(ax, b["bbox_uv"], edgecolor="lime", lw=1.5)
            cp, rp = uv_to_pixel(0.02, b["centre_v"])
            ax.text(cp, rp, f"band #{i+1} "
                    f"pitch_u={b['pad_pitch']['pitch_u_px'] if b['pad_pitch'] else '?'}",
                    color="lime", fontsize=8, va="center")
    if "columns" in features and features["columns"].get("found"):
        for i, c in enumerate(features["columns"]["columns"]):
            _draw_bbox_uv(ax, c["bbox_uv"], edgecolor="orange", lw=1.5)
            cp, rp = uv_to_pixel(c["centre_u"], 0.95)
            ax.text(cp, rp, f"col #{i+1}",
                    color="orange", fontsize=8, ha="center")
    ax.set_title(f"Die {label} — {description}", fontsize=10)
    ax.set_xlim(0, OUT_SIZE)
    ax.set_ylim(OUT_SIZE, 0)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def main() -> int:
    rgb = np.asarray(Image.open(PHOTO_PATH).convert("RGB"), dtype=np.float32)
    gray = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1]
            + 0.114 * rgb[..., 2]).astype(np.float32)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    atlas = {"die_types": {}, "grid": {
        "theta_deg_cw": 4.665, "x0": GRID_X0, "y0": GRID_Y0,
        "d_col": D_COL.tolist(), "d_row": D_ROW.tolist(),
    }}

    # --- 4D (col_label 4 = type 0 wide, row_label 3 = type 3) ---
    print("=== 4D ===")
    crop_4d = extract_die_crop(gray, 4, 3)
    bar = find_vertical_bar(crop_4d)
    print(f"  bar: {bar}")
    atlas["die_types"]["(0, 3)"] = {
        "instances_in_photo": ["0D", "4D", "8D"],
        "user_description": "strong vertical bar around (u 0.3-0.35, v 0.4-0.6), otherwise small features",
        "features": [bar],
    }
    save_die_overlay(crop_4d, "4D", {"bar": bar},
                     OUT_DIR / "die_4D.png",
                     "vertical bar (slanted-edge target)")
    Image.fromarray(crop_4d.clip(0, 255).astype(np.uint8)).save(
        OUT_DIR / "die_4D_crop.png")

    # --- 3E (col_label 3 = type 3, row_label 4 = type 0) ---
    print("\n=== 3E ===")
    crop_3e = extract_die_crop(gray, 3, 4)
    bands = find_horizontal_pad_bands(crop_3e, n_bands=3)
    print(f"  bands: {bands.get('n_bands_detected')} detected")
    for b in bands.get("bands", []):
        print(f"    {b}")
    atlas["die_types"]["(3, 0)"] = {
        "instances_in_photo": ["3E", "7E"],
        "user_description": "bond pads in three horizontal bands across entire die",
        "features": [bands],
    }
    save_die_overlay(crop_3e, "3E", {"bands": bands},
                     OUT_DIR / "die_3E.png",
                     "3 horizontal pad bands (vertical-direction FFT)")
    Image.fromarray(crop_3e.clip(0, 255).astype(np.uint8)).save(
        OUT_DIR / "die_3E_crop.png")

    # --- 3C (col_label 3, row_label 2) ---
    print("\n=== 3C ===")
    crop_3c = extract_die_crop(gray, 3, 2)
    cols = find_pad_columns(crop_3c, n_cols=3,
                            u_range=(0.0, 1.0), v_range=(0.0, 0.7))
    print(f"  columns: {cols.get('n_columns_detected')} detected")
    for c in cols.get("columns", []):
        print(f"    {c}")
    atlas["die_types"]["(3, 2)"] = {
        "instances_in_photo": ["3C", "7C"],
        "user_description": "three pad columns u 0-1, v 0-0.7; irregular row u 0.7-1, v 0-1",
        "features": [cols],
    }
    save_die_overlay(crop_3c, "3C", {"columns": cols},
                     OUT_DIR / "die_3C.png",
                     "3 pad columns (horizontal-direction FFT)")
    Image.fromarray(crop_3c.clip(0, 255).astype(np.uint8)).save(
        OUT_DIR / "die_3C_crop.png")

    atlas_path = OUT_DIR / "atlas_top3.json"
    with open(atlas_path, "w") as f:
        json.dump(atlas, f, indent=2, default=lambda o: o.tolist() if hasattr(o, "tolist") else o)
    print(f"\nSaved atlas: {atlas_path}")
    print(f"Saved overlays: die_4D.png, die_3E.png, die_3C.png in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
