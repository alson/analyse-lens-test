"""Parse user-painted feature regions on 0129_painted.png.

Reads the painted PNG (same resolution as step_0129_b.jpg) where the
user has covered features with one of three solid colours:

  Magenta #FF00FF  →  bond-pad regions
  Yellow  #FFFF00  →  isolated bars / slanted-edge candidates
  Cyan    #00FFFF  →  experimental "try this" regions

For each connected component of each colour:
  - bbox in image pixels
  - bbox in atlas (cl, rl, u, v) coords using the 0129 grid params
  - die-instance identifier (which die the component falls inside)
  - super-cell type (col mod 4, row mod 4) for inheritance
  - 2D-FFT pad pitch_u / pitch_v computed on the ORIGINAL image inside
    the magenta region (skipped for yellow / cyan)

Writes:
  - atlas_0129_painted.json
  - verify_0129_painted.png (original photo + painted bboxes overlay)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.ndimage import label


PHOTO_PATH = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-13/"
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S + 35mm extension/f_11/prev_step_0129_b.jpg"
)
PAINTED_PATH = Path(__file__).parent.parent / "in" / "0129_painted2.png"
GRID_JSON = Path(__file__).parent.parent / "out" / "0129" / "grid_params.json"
OUT_DIR = Path(__file__).parent.parent / "out" / "0129"

COLOURS = {
    "bond_pads":         (255,   0, 255),  # magenta — hue ~300°
    "slanted_edge":      (255, 255,   0),  # yellow  — hue ~60°
    "experimental":      (  0, 255, 255),  # cyan    — hue ~180°
}
# HSV-based detection. (hue_centre, hue_halfwidth, min_sat, min_val).
# Tolerant of partial transparency / blended paint.
HSV_RULES = {
    "bond_pads":    {"hue_centre": 300, "hue_halfwidth": 30, "min_sat": 0.35, "min_val": 0.30},
    "slanted_edge": {"hue_centre": 60,  "hue_halfwidth": 15, "min_sat": 0.70, "min_val": 0.50},
    "experimental": {"hue_centre": 180, "hue_halfwidth": 30, "min_sat": 0.30, "min_val": 0.35},
}

D_COL_OVERVIEW = np.array([539.02, 457.54, 453.95, 453.24])
D_ROW_OVERVIEW = np.array([455.88, 543.88, 452.83, 452.19])

MIN_COMPONENT_AREA_PX = 5000  # ignore stray pixels / small paint slips / JPEG noise


def _cum(d4, k):
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


def image_to_atlas(x, y, params):
    """Inverse of grid_xy: image (x, y) → (col_line_real, row_line_real).

    Uses cumulative widths to invert. col_line is the floating-point grid
    position (e.g. 4.37 = 37% of the way through col 4).
    """
    theta = params["theta_rad"]
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    x0, y0 = params["x0"], params["y0"]
    d_col = np.array(params["d_col"])
    d_row = np.array(params["d_row"])
    dx, dy = x - x0, y - y0
    # u = cos_t * u_cum + sin_t * v_cum; y - y0 = sin_t * u_cum - cos_t * v_cum.
    # Solve [[cos_t, sin_t], [sin_t, -cos_t]] @ [u_cum, v_cum] = [dx, dy]
    det = -cos_t ** 2 - sin_t ** 2  # = -1
    u_cum = (-cos_t * dx - sin_t * dy) / det
    v_cum = (-sin_t * dx + cos_t * dy) / det
    # Now invert u_cum → col_line, v_cum → row_line
    cl = _invert_cum(u_cum, d_col)
    rl = _invert_cum(v_cum, d_row)
    return cl, rl


def _invert_cum(target, d4):
    """Return real-valued k such that _cum(d4, k) == target."""
    if target <= 0:
        return target / d4[0]
    super_cell = d4.sum()
    full = int(target // super_cell)
    remainder = target - full * super_cell
    k = full * 4
    for i in range(4):
        if remainder <= d4[i]:
            return k + remainder / d4[i]
        remainder -= d4[i]
        k += 1
    return float(k)


def _rgb_to_hsv(rgb_uint8):
    """Convert HxWx3 uint8 RGB → (hue_deg [0,360), sat [0,1], val [0,1])."""
    r = rgb_uint8[..., 0].astype(np.float32) / 255.0
    g = rgb_uint8[..., 1].astype(np.float32) / 255.0
    b = rgb_uint8[..., 2].astype(np.float32) / 255.0
    cmax = np.maximum(np.maximum(r, g), b)
    cmin = np.minimum(np.minimum(r, g), b)
    delta = cmax - cmin
    hue = np.zeros_like(cmax)
    # avoid div by zero
    nz = delta > 1e-6
    # Compute hue piecewise
    rmax = (cmax == r) & nz
    gmax = (cmax == g) & nz
    bmax = (cmax == b) & nz
    hue[rmax] = (60 * ((g - b) / delta)[rmax]) % 360
    hue[gmax] = (60 * ((b - r) / delta)[gmax] + 120) % 360
    hue[bmax] = (60 * ((r - g) / delta)[bmax] + 240) % 360
    sat = np.where(cmax > 0, delta / np.maximum(cmax, 1e-6), 0)
    val = cmax
    return hue, sat, val


def _hue_in_range(hue, centre, halfwidth):
    """Circular hue check."""
    diff = np.abs(((hue - centre + 180) % 360) - 180)
    return diff <= halfwidth


def find_color_components(painted, kind, hsv,
                          min_area=MIN_COMPONENT_AREA_PX):
    """Return components matching HSV_RULES[kind]."""
    rule = HSV_RULES[kind]
    hue, sat, val = hsv
    mask = (_hue_in_range(hue, rule["hue_centre"], rule["hue_halfwidth"])
            & (sat >= rule["min_sat"])
            & (val >= rule["min_val"]))
    labeled, n = label(mask)
    components = []
    for i in range(1, n + 1):
        rs, cs = np.where(labeled == i)
        if len(rs) < min_area:
            continue
        components.append({
            "area_px": int(len(rs)),
            "bbox_image": [int(cs.min()), int(rs.min()),
                            int(cs.max()), int(rs.max())],  # x_min, y_min, x_max, y_max
            "centre_image": [float(cs.mean()), float(rs.mean())],
            "mask_indices": (rs, cs),
        })
    components.sort(key=lambda c: -c["area_px"])
    return components


def _pad_pitch(strip):
    H, W = strip.shape
    if H < 16 or W < 16:
        return None
    s = strip.astype(np.float32) - strip.mean()
    han = np.outer(np.hanning(H), np.hanning(W)).astype(np.float32)
    s = s * han
    F = np.fft.fftshift(np.fft.fft2(s))
    mag = np.abs(F)
    cy, cx = H // 2, W // 2
    rr = np.indices(mag.shape)
    r = np.sqrt((rr[0] - cy) ** 2 + (rr[1] - cx) ** 2)
    mag[r < 4] = 0
    u_prof = mag[cy, cx + 4:cx + W // 2]
    pitch_u = W / (int(np.argmax(u_prof)) + 4) if u_prof.size and u_prof.max() > 0 else None
    v_prof = mag[cy + 4:cy + H // 2, cx]
    pitch_v = H / (int(np.argmax(v_prof)) + 4) if v_prof.size and v_prof.max() > 0 else None
    return {
        "pitch_u_px": round(pitch_u, 2) if pitch_u else None,
        "pitch_v_px": round(pitch_v, 2) if pitch_v else None,
    }


def _die_from_atlas(cl_real, rl_real, n_col=11, n_row=6):
    """Return die label like '4D' from real-valued (cl, rl).

    Die (col, row) is the one whose bottom-left corner is at integer
    (col_line=col, row_line=row). The die contains cl ∈ [col, col+1)
    and rl ∈ [row, row+1).
    """
    col = int(np.floor(cl_real))
    row = int(np.floor(rl_real))
    if col < 0 or col > n_col or row < 0 or row > n_row:
        return None, None, None
    row_letter = "ABCDEF"[row] if 0 <= row <= 5 else f"r{row}"
    return col, row, f"{col}{row_letter}"


def parse_components(components, photo_gray, params, kind, compute_pitch=False):
    """For each connected component, compute atlas coords and per-component metadata."""
    entries = []
    for comp in components:
        x_min, y_min, x_max, y_max = comp["bbox_image"]
        # Atlas coords of bbox corners
        cl_tl, rl_tl = image_to_atlas(x_min, y_min, params)  # top-left in image
        cl_tr, rl_tr = image_to_atlas(x_max, y_min, params)
        cl_bl, rl_bl = image_to_atlas(x_min, y_max, params)
        cl_br, rl_br = image_to_atlas(x_max, y_max, params)
        cl_min = min(cl_tl, cl_bl)
        cl_max = max(cl_tr, cl_br)
        # rl is inverted: y_min in image = TOP = higher row_line
        rl_max = max(rl_tl, rl_tr)
        rl_min = min(rl_bl, rl_br)
        # Die assignment from centre
        cx, cy = comp["centre_image"]
        cl_c, rl_c = image_to_atlas(cx, cy, params)
        col, row, die_label = _die_from_atlas(cl_c, rl_c)
        if die_label is None:
            continue
        die_type = (col % 4, row % 4)
        # u, v within the centre die
        u = cl_c - col
        v = rl_c - row
        # Convert bbox corners to die-internal (u, v) — clamp to the die
        u_min = max(0.0, cl_min - col)
        u_max = min(1.0, cl_max - col)
        v_min = max(0.0, rl_min - row)
        v_max = min(1.0, rl_max - row)
        entry = {
            "kind": kind,
            "die_label": die_label,
            "die_type": list(die_type),
            "bbox_uv_in_die": [round(u_min, 3), round(v_min, 3),
                                round(u_max, 3), round(v_max, 3)],
            "centre_uv_in_die": [round(u, 3), round(v, 3)],
            "bbox_image": comp["bbox_image"],
            "area_px": comp["area_px"],
        }
        if compute_pitch:
            rs, cs = comp["mask_indices"]
            r0, r1 = int(rs.min()), int(rs.max())
            c0, c1 = int(cs.min()), int(cs.max())
            strip = photo_gray[r0:r1 + 1, c0:c1 + 1]
            # Use only painted pixels for the pitch — set others to mean
            comp_mask = np.zeros_like(strip, dtype=bool)
            comp_mask[rs - r0, cs - c0] = True
            strip_for_fft = strip.copy()
            strip_for_fft[~comp_mask] = strip[comp_mask].mean()
            entry["pad_pitch_px"] = _pad_pitch(strip_for_fft)
        entries.append(entry)
    return entries


def main():
    if not PAINTED_PATH.exists():
        print(f"Painted PNG not found at {PAINTED_PATH}")
        print("Save your painted file there, then re-run.")
        return 1
    painted = np.asarray(Image.open(PAINTED_PATH).convert("RGB"))
    print(f"Loaded painted: {painted.shape}")
    photo_rgb = np.asarray(Image.open(PHOTO_PATH).convert("RGB"))
    photo_gray = (0.299 * photo_rgb[..., 0]
                  + 0.587 * photo_rgb[..., 1]
                  + 0.114 * photo_rgb[..., 2]).astype(np.float32)
    if painted.shape[:2] != photo_rgb.shape[:2]:
        print(f"WARN: painted resolution {painted.shape[:2]} != original "
              f"{photo_rgb.shape[:2]}")
    with open(GRID_JSON) as f:
        params = json.load(f)

    atlas = {
        "source_photo": str(PHOTO_PATH),
        "painted_overlay": str(PAINTED_PATH),
        "grid_params": params,
        "features_by_die_type": {},
        "raw_components": {},
    }

    hsv = _rgb_to_hsv(painted)
    all_entries = []
    for kind, rgb in COLOURS.items():
        comps = find_color_components(painted, kind, hsv)
        rule = HSV_RULES[kind]
        print(f"\n{kind:>15s} (hue {rule['hue_centre']}°±{rule['hue_halfwidth']}, "
              f"sat≥{rule['min_sat']}, val≥{rule['min_val']}): {len(comps)} components")
        entries = parse_components(
            comps, photo_gray, params, kind,
            compute_pitch=(kind in ("bond_pads", "experimental")))
        atlas["raw_components"][kind] = entries
        all_entries.extend(entries)
        for e in entries[:10]:
            ptxt = ""
            if e.get("pad_pitch_px"):
                ptxt = f"  pitch=({e['pad_pitch_px']['pitch_u_px']},{e['pad_pitch_px']['pitch_v_px']})"
            print(f"  {e['die_label']} type={e['die_type']}"
                  f"  bbox_uv={e['bbox_uv_in_die']}"
                  f"  area={e['area_px']}{ptxt}")

    # Group by die_type for inheritance
    for entry in all_entries:
        key = str(tuple(entry["die_type"]))
        atlas["features_by_die_type"].setdefault(key, []).append({
            k: entry[k] for k in
            ("kind", "die_label", "bbox_uv_in_die", "centre_uv_in_die",
             "area_px", "pad_pitch_px")
            if k in entry
        })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    atlas_path = OUT_DIR / "atlas_0129_painted.json"
    with open(atlas_path, "w") as f:
        json.dump(atlas, f, indent=2,
                  default=lambda o: o.tolist() if hasattr(o, "tolist") else float(o))
    print(f"\nSaved: {atlas_path}")

    # Verification overlay
    fig, ax = plt.subplots(figsize=(20, 14))
    ax.imshow(photo_rgb)
    colour_map = {"bond_pads": "magenta", "slanted_edge": "yellow",
                  "experimental": "cyan"}
    for kind, entries in atlas["raw_components"].items():
        col = colour_map[kind]
        for e in entries:
            x0, y0, x1, y1 = e["bbox_image"]
            ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0,
                                        fill=False, edgecolor=col, lw=1.5))
            ax.text(x0, y0 - 4, f"{e['die_label']} {kind}", color=col,
                    fontsize=8,
                    bbox=dict(boxstyle="round,pad=0.15", fc="black",
                              ec="none", alpha=0.5))
    ax.set_title(f"Painted-feature parse — {sum(len(v) for v in atlas['raw_components'].values())} components")
    ax.set_xlim(0, photo_rgb.shape[1])
    ax.set_ylim(photo_rgb.shape[0], 0)
    out_png = OUT_DIR / "verify_0129_painted.png"
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    plt.close(fig)
    print(f"Saved: {out_png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
