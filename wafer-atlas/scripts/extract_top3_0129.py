"""Re-run top-3 CV on higher-resolution 0129 die crops.

Uses the v2 envelope-detection + connected-components approach from
extract_top3_v2.py, but on the 0129 die crops at OUT_SIZE=900 (vs
overview's 600). With ~1.6× the pixel density, the pad bands should
resolve cleanly and the CV bboxes should track actual envelopes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, label, map_coordinates
from scipy.signal import find_peaks


PHOTO_PATH = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-05-13/"
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S + 35mm extension/f_11/prev_step_0129_b.jpg"
)
GRID_JSON = Path(__file__).parent.parent / "out" / "0129" / "grid_params.json"
OUT_DIR = Path(__file__).parent.parent / "out" / "0129"

OUT_SIZE = 900
MARGIN = 0.05


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


def extract_die_crop(image, cl_label, rl_label, params,
                     out_size=OUT_SIZE, margin=MARGIN):
    theta = params["theta_rad"]
    x0, y0 = params["x0"], params["y0"]
    d_col = np.array(params["d_col"])
    d_row = np.array(params["d_row"])
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    base_u = _cum(d_col, cl_label)
    base_v = _cum(d_row, rl_label)
    du = d_col[cl_label % 4]
    dv = d_row[rl_label % 4]
    u_range = np.linspace(-margin, 1 + margin, out_size)
    v_range = np.linspace(1 + margin, -margin, out_size)
    U, V = np.meshgrid(u_range, v_range)
    u_cum = base_u + U * du
    v_cum = base_v + V * dv
    x_image = x0 + cos_t * u_cum + sin_t * v_cum
    y_image = y0 + sin_t * u_cum - cos_t * v_cum
    coords = np.stack([y_image.ravel(), x_image.ravel()])
    sampled = map_coordinates(image, coords, order=1, mode="nearest")
    return sampled.reshape(out_size, out_size).astype(np.float32)


def uv_to_pixel(u, v, out_size=OUT_SIZE, margin=MARGIN):
    col_pix = (u + margin) / (1 + 2 * margin) * (out_size - 1)
    row_pix = (1 + margin - v) / (1 + 2 * margin) * (out_size - 1)
    return col_pix, row_pix


def pixel_to_uv(col_pix, row_pix, out_size=OUT_SIZE, margin=MARGIN):
    u = col_pix / (out_size - 1) * (1 + 2 * margin) - margin
    v = 1 + margin - row_pix / (out_size - 1) * (1 + 2 * margin)
    return u, v


def find_dark_bar(crop, search_uv=(0.15, 0.15, 0.85, 0.85),
                  min_area_px=2000, min_aspect=1.5):
    u_lo, v_lo, u_hi, v_hi = search_uv
    c_lo = int(uv_to_pixel(u_lo, 0)[0])
    c_hi = int(uv_to_pixel(u_hi, 0)[0])
    r_hi = int(uv_to_pixel(0, v_lo)[1])
    r_lo = int(uv_to_pixel(0, v_hi)[1])
    patch = crop[r_lo:r_hi, c_lo:c_hi]
    bg = float(np.median(patch))
    std = float(patch.std())
    thresh = bg - 1.0 * std
    mask = patch < thresh
    if mask.sum() < min_area_px:
        return {"found": False}
    labeled, n = label(mask)
    candidates = []
    for i in range(1, n + 1):
        rs, cs = np.where(labeled == i)
        if len(rs) < min_area_px:
            continue
        r_min, r_max = int(rs.min()), int(rs.max())
        c_min, c_max = int(cs.min()), int(cs.max())
        h, w = r_max - r_min + 1, c_max - c_min + 1
        aspect = h / max(w, 1)
        if aspect < min_aspect:
            continue
        candidates.append({
            "area_px": int(len(rs)),
            "h_px": h, "w_px": w, "aspect": aspect,
            "score": float(len(rs) * aspect),
            "r_min": r_min, "r_max": r_max,
            "c_min": c_min, "c_max": c_max,
        })
    if not candidates:
        return {"found": False}
    candidates.sort(key=lambda c: -c["score"])
    best = candidates[0]
    rect_c_lo = c_lo + best["c_min"]
    rect_c_hi = c_lo + best["c_max"]
    rect_r_lo = r_lo + best["r_min"]
    rect_r_hi = r_lo + best["r_max"]
    u_min, v_max = pixel_to_uv(rect_c_lo, rect_r_lo)
    u_max, v_min = pixel_to_uv(rect_c_hi, rect_r_hi)
    return {
        "found": True, "polarity": "dark",
        "bbox_uv": [round(u_min, 3), round(v_min, 3),
                    round(u_max, 3), round(v_max, 3)],
        "bbox_px": [rect_c_lo, rect_r_lo, rect_c_hi, rect_r_hi],
        "size_px": [best["w_px"], best["h_px"]],
        "aspect": round(best["aspect"], 2),
    }


def find_pad_bands_envelope(crop, axis="horizontal", n_bands=3,
                            smooth_sigma=25, density_thresh=0.30):
    """Find broad pad-band envelopes by thresholding density.

    Threshold density at density_thresh × max, then find contiguous high-
    density regions. n_bands largest are kept.
    """
    bg = float(np.median(crop))
    std = float(crop.std())
    bright = crop > bg + 0.5 * std
    if axis == "horizontal":
        density = bright.mean(axis=1).astype(np.float32)
    else:
        density = bright.mean(axis=0).astype(np.float32)
    smoothed = gaussian_filter(density, sigma=smooth_sigma, mode="nearest")
    thresh = density_thresh * smoothed.max()
    above = smoothed > thresh
    # Find contiguous runs of True
    runs = []
    i = 0
    N = len(above)
    while i < N:
        if above[i]:
            j = i
            while j < N and above[j]:
                j += 1
            runs.append((i, j - 1, j - i))
            i = j
        else:
            i += 1
    if len(runs) < n_bands:
        return {"found": False, "n_detected": len(runs), "thresh": float(thresh)}
    # Keep top n by length
    runs.sort(key=lambda r: -r[2])
    keep = sorted(runs[:n_bands], key=lambda r: r[0])
    bands = []
    for (lo, hi, w) in keep:
        if axis == "horizontal":
            u_min, v_top = pixel_to_uv(0, lo)
            u_max, v_bot = pixel_to_uv(OUT_SIZE - 1, hi)
            bbox = [round(u_min, 3), round(v_bot, 3),
                    round(u_max, 3), round(v_top, 3)]
            bbox_px = [0, lo, OUT_SIZE - 1, hi]
            sub_crop = crop[lo:hi + 1, :]
        else:
            u_lo, _ = pixel_to_uv(lo, 0)
            u_hi, _ = pixel_to_uv(hi, 0)
            bbox = [round(u_lo, 3), 0.0, round(u_hi, 3), 1.0]
            bbox_px = [lo, 0, hi, OUT_SIZE - 1]
            sub_crop = crop[:, lo:hi + 1]
        pitch = _pad_pitch(sub_crop)
        bands.append({"bbox_uv": bbox, "bbox_px": bbox_px,
                      "width_px": int(w), "pad_pitch": pitch})
    if axis == "horizontal":
        bands.sort(key=lambda b: -((b["bbox_uv"][1] + b["bbox_uv"][3]) / 2))
    else:
        bands.sort(key=lambda b: (b["bbox_uv"][0] + b["bbox_uv"][2]) / 2)
    return {"found": True, "n_detected": len(bands), "bands": bands,
            "thresh": float(thresh)}


def _pad_pitch(strip):
    H, W = strip.shape
    if H < 16 or W < 16:
        return None
    s = strip - strip.mean()
    han = np.outer(np.hanning(H), np.hanning(W)).astype(np.float32)
    s = s * han
    F = np.fft.fftshift(np.fft.fft2(s))
    mag = np.abs(F)
    cy, cx = H // 2, W // 2
    rr = np.indices(mag.shape)
    r = np.sqrt((rr[0] - cy) ** 2 + (rr[1] - cx) ** 2)
    mag[r < 4] = 0
    u_prof = mag[cy, cx + 4:cx + W // 2]
    if u_prof.size and u_prof.max() > 0:
        peak_u = int(np.argmax(u_prof)) + 4
        pitch_u = W / peak_u
    else:
        pitch_u = None
    v_prof = mag[cy + 4:cy + H // 2, cx]
    if v_prof.size and v_prof.max() > 0:
        peak_v = int(np.argmax(v_prof)) + 4
        pitch_v = H / peak_v
    else:
        pitch_v = None
    return {"pitch_u_px": round(pitch_u, 2) if pitch_u else None,
            "pitch_v_px": round(pitch_v, 2) if pitch_v else None}


def _draw_bbox_uv(ax, bbox_uv, **kw):
    u_min, v_min, u_max, v_max = bbox_uv
    c_lo, r_hi = uv_to_pixel(u_min, v_min)
    c_hi, r_lo = uv_to_pixel(u_max, v_max)
    ax.add_patch(plt.Rectangle((c_lo, r_lo), c_hi - c_lo, r_hi - r_lo,
                                fill=False, **kw))


def save_overlay(crop, label_str, features, out_path, description):
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.imshow(crop, cmap="gray")
    for u in np.arange(0.0, 1.001, 0.2):
        cp, _ = uv_to_pixel(u, 0.5)
        ax.axvline(cp, color="cyan", lw=0.3, alpha=0.4)
        ax.text(cp, OUT_SIZE - 5, f"u={u:.1f}", color="cyan", fontsize=8,
                ha="center", va="top")
    for v in np.arange(0.0, 1.001, 0.2):
        _, rp = uv_to_pixel(0.5, v)
        ax.axhline(rp, color="cyan", lw=0.3, alpha=0.4)
        ax.text(5, rp, f"v={v:.1f}", color="cyan", fontsize=8,
                ha="left", va="center")
    if "bar" in features and features["bar"].get("found"):
        bar = features["bar"]
        _draw_bbox_uv(ax, bar["bbox_uv"], edgecolor="yellow", lw=2.5)
        u_min, v_min, u_max, v_max = bar["bbox_uv"]
        ax.text(uv_to_pixel(u_min, v_max)[0],
                uv_to_pixel(u_min, v_max)[1] - 8,
                f"bar [{u_min:.2f},{v_min:.2f}]–[{u_max:.2f},{v_max:.2f}]"
                f" aspect={bar['aspect']:.1f} {bar['size_px']}px",
                color="yellow", fontsize=10, va="bottom")
    for kind, color in (("bands", "lime"), ("columns", "orange")):
        if kind in features and features[kind].get("found"):
            for i, b in enumerate(features[kind]["bands"]):
                _draw_bbox_uv(ax, b["bbox_uv"], edgecolor=color, lw=1.8)
                u_min, v_min, u_max, v_max = b["bbox_uv"]
                p = b.get("pad_pitch") or {}
                ptxt = ""
                if kind == "bands" and p.get("pitch_u_px"):
                    ptxt = f"  pitch_u={p['pitch_u_px']:.0f}, pitch_v={p['pitch_v_px']:.0f}"
                elif kind == "columns" and p.get("pitch_v_px"):
                    ptxt = f"  pitch_v={p['pitch_v_px']:.0f}, pitch_u={p['pitch_u_px']:.0f}"
                if kind == "bands":
                    cp, rp = uv_to_pixel(0.02, (v_min + v_max) / 2)
                    ax.text(cp, rp,
                            f"#{i+1} v∈[{v_min:.2f},{v_max:.2f}]{ptxt}",
                            color=color, fontsize=9, va="center")
                else:
                    cp, rp = uv_to_pixel((u_min + u_max) / 2, 0.97)
                    ax.text(cp, rp,
                            f"#{i+1} u∈[{u_min:.2f},{u_max:.2f}]{ptxt}",
                            color=color, fontsize=9, ha="center")
    ax.set_title(f"Die {label_str} on 0129 — {description}", fontsize=11)
    ax.set_xlim(0, OUT_SIZE)
    ax.set_ylim(OUT_SIZE, 0)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def main():
    rgb = np.asarray(Image.open(PHOTO_PATH).convert("RGB"), dtype=np.float32)
    gray = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1]
            + 0.114 * rgb[..., 2]).astype(np.float32)
    with open(GRID_JSON) as f:
        params = json.load(f)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    atlas = {"die_types": {}, "source_photo": str(PHOTO_PATH), "grid": params}

    # 4D
    print("=== 4D (vertical bar) ===")
    crop_4d = extract_die_crop(gray, 4, 3, params)
    bar = find_dark_bar(crop_4d, search_uv=(0.15, 0.15, 0.85, 0.85))
    print(f"  bar: {bar}")
    save_overlay(crop_4d, "4D", {"bar": bar}, OUT_DIR / "die_4D.png",
                 "vertical bar (slanted-edge target)")
    atlas["die_types"]["(0, 3)"] = {"label": "4D", "feature": bar}

    # 3E
    print("\n=== 3E (3 horizontal pad bands) ===")
    crop_3e = extract_die_crop(gray, 3, 4, params)
    bands = find_pad_bands_envelope(crop_3e, axis="horizontal", n_bands=3)
    print(f"  bands: {bands.get('n_detected')} detected")
    for b in bands.get("bands", []):
        print(f"    {b}")
    save_overlay(crop_3e, "3E", {"bands": bands}, OUT_DIR / "die_3E.png",
                 "3 horizontal pad bands")
    atlas["die_types"]["(3, 0)"] = {"label": "3E", "feature": bands}

    # 3C
    print("\n=== 3C (3 pad columns) ===")
    crop_3c = extract_die_crop(gray, 3, 2, params)
    cols = find_pad_bands_envelope(crop_3c, axis="vertical", n_bands=3)
    print(f"  columns: {cols.get('n_detected')} detected")
    for b in cols.get("bands", []):
        print(f"    {b}")
    save_overlay(crop_3c, "3C", {"columns": cols}, OUT_DIR / "die_3C.png",
                 "3 pad columns")
    atlas["die_types"]["(3, 2)"] = {"label": "3C", "feature": cols}

    atlas_path = OUT_DIR / "atlas_top3.json"
    with open(atlas_path, "w") as f:
        json.dump(atlas, f, indent=2,
                  default=lambda o: o.tolist() if hasattr(o, "tolist") else float(o))
    print(f"\nSaved atlas: {atlas_path}")
    print(f"Overlays in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
