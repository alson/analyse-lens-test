"""Task 12: Re-point POC B (pad-grid FFT) at atlas features for sweep 1.

For each atlas bond-pad-band feature, use sweep 1's anchor-based affine to
predict the band's location in each shot's image, extract the ROI, and
compute the pad-FFT amplitude at the atlas-known pitch. Plot the per-shot
amplitude signal and find argmax.

Compare to:
  - LSF argmax shot 137 (Method-B baseline that this is meant to confirm)
  - POC B original argmax shot 119 (which used a 1024² ROI at the centre tile)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


ATLAS_PATH = Path(__file__).parent.parent / "atlas.json"
ANCHORS_PATH = Path(__file__).parent.parent / "out" / "sweep_anchors" / "anchor_fit_params.json"

SWEEP_NAME = "sweep1_M0.385"
SWEEP_DIR = Path(
    "/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29/"
    "NIKKOR Z 100-400mm f_4.5-5.6 VR S/1_2.60/F11"
)

OUT_DIR = Path(__file__).parent.parent / "out" / "task12"

LSF_ARGMAX_SHOT = 137  # ground-truth-ish from current LSF pipeline
POC_B_ARGMAX_SHOT = 119  # POC B's 1024² centre-ROI result


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


def die_uv_to_sweep_image(col_label, row_label, u, v, sweep_affine, atlas):
    """Die-internal (col, row, u, v) → sweep image (x, y)."""
    d_col = atlas["die_pitch_px_in_0129"]["d_col"]
    d_row = atlas["die_pitch_px_in_0129"]["d_row"]
    theta = sweep_affine["theta_rad"]
    x0, y0 = sweep_affine["x0_img"], sweep_affine["y0_img"]
    scale = sweep_affine["scale"]
    cl = col_label + u
    rl = row_label + v
    u_c = scale * _cum(d_col, cl)
    v_c = scale * _cum(d_row, rl)
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    return (x0 + cos_t * u_c + sin_t * v_c,
            y0 + sin_t * u_c - cos_t * v_c)


def extract_feature_roi(image, feature_bbox_uv, col_label, row_label,
                        sweep_affine, atlas, margin_px=10):
    u_min, v_min, u_max, v_max = feature_bbox_uv
    corners = []
    for u in [u_min, u_max]:
        for v in [v_min, v_max]:
            corners.append(die_uv_to_sweep_image(col_label, row_label, u, v,
                                                  sweep_affine, atlas))
    corners = np.array(corners)
    x_lo = max(0, int(corners[:, 0].min() - margin_px))
    x_hi = min(image.shape[1], int(corners[:, 0].max() + margin_px))
    y_lo = max(0, int(corners[:, 1].min() - margin_px))
    y_hi = min(image.shape[0], int(corners[:, 1].max() + margin_px))
    if x_hi - x_lo < 64 or y_hi - y_lo < 64:
        return None, None
    return image[y_lo:y_hi, x_lo:x_hi], (x_lo, y_lo, x_hi, y_hi)


def pad_fft_amplitude(roi, pitch_u_px, pitch_v_px, half_bandwidth_cy_per_px=0.005):
    """Sum |FFT| amplitude at predicted pad fundamental (and its mirror)."""
    if roi.ndim == 3:
        roi = 0.299 * roi[..., 0] + 0.587 * roi[..., 1] + 0.114 * roi[..., 2]
    roi = roi.astype(np.float32)
    H, W = roi.shape
    s = roi - roi.mean()
    han = np.outer(np.hanning(H), np.hanning(W)).astype(np.float32)
    s = s * han
    F = np.fft.fftshift(np.fft.fft2(s))
    mag = np.abs(F)
    cy, cx = H // 2, W // 2

    expected_peaks = []
    if pitch_u_px and pitch_u_px > 0:
        fu = 1.0 / pitch_u_px
        kx = fu * W
        expected_peaks.extend([(kx, 0), (-kx, 0)])
    if pitch_v_px and pitch_v_px > 0:
        fv = 1.0 / pitch_v_px
        ky = fv * H
        expected_peaks.extend([(0, ky), (0, -ky)])
    if pitch_u_px and pitch_v_px and pitch_u_px > 0 and pitch_v_px > 0:
        fu = 1.0 / pitch_u_px
        fv = 1.0 / pitch_v_px
        kx, ky = fu * W, fv * H
        for sx in [1, -1]:
            for sy in [1, -1]:
                expected_peaks.append((sx * kx, sy * ky))

    if not expected_peaks:
        return None

    bw_px_x = half_bandwidth_cy_per_px * W
    bw_px_y = half_bandwidth_cy_per_px * H
    total_amp = 0.0
    n_pixels = 0
    for kx_exp, ky_exp in expected_peaks:
        x_lo = max(0, int(cx + kx_exp - bw_px_x))
        x_hi = min(W, int(cx + kx_exp + bw_px_x) + 1)
        y_lo = max(0, int(cy + ky_exp - bw_px_y))
        y_hi = min(H, int(cy + ky_exp + bw_px_y) + 1)
        if x_hi > x_lo and y_hi > y_lo:
            patch = mag[y_lo:y_hi, x_lo:x_hi]
            total_amp += patch.sum()
            n_pixels += patch.size
    return float(total_amp / max(n_pixels, 1))


def collect_pad_pad_features(atlas):
    features = []
    for type_key, info in atlas["die_types"].items():
        for bp in info["feature_inventory"]["bond_pads"]:
            pp = bp.get("pad_pitch_px") or {}
            if not pp.get("pitch_u_px") and not pp.get("pitch_v_px"):
                continue
            source_die = bp.get("source_die", "")
            if len(source_die) < 2:
                continue
            try:
                col_label = int(source_die[:-1])
                row_letter = source_die[-1]
                row_label = "ABCDEF".index(row_letter)
            except (ValueError, KeyError):
                continue
            features.append({
                "type_key": type_key,
                "die_label": source_die,
                "col_label": col_label,
                "row_label": row_label,
                "bbox_uv": bp["bbox_uv"],
                "pitch_u_atlas": pp.get("pitch_u_px"),
                "pitch_v_atlas": pp.get("pitch_v_px"),
                "area_px": bp["area_px"],
            })
    features.sort(key=lambda f: -f["area_px"])
    return features


def main():
    atlas = json.load(open(ATLAS_PATH))
    anchors = json.load(open(ANCHORS_PATH))
    sweep_affine = anchors[SWEEP_NAME]
    print(f"Sweep {SWEEP_NAME}: θ={sweep_affine['theta_deg']:.3f}° "
          f"scale={sweep_affine['scale']:.4f} "
          f"origin=({sweep_affine['x0_img']:.0f}, {sweep_affine['y0_img']:.0f})")

    features = collect_pad_pad_features(atlas)
    print(f"\n{len(features)} bond-pad features with FFT pitches in atlas")
    # Pick top 5 by area for the per-shot scan
    N_TOP = 5
    top_features = features[:N_TOP]
    for f in top_features:
        print(f"  {f['die_label']} type={f['type_key']} "
              f"pitch_u_atlas={f['pitch_u_atlas']} pitch_v_atlas={f['pitch_v_atlas']} "
              f"area={f['area_px']}")

    # Validate that each top feature's predicted image position is INSIDE sweep 1's image
    shot_paths = sorted(SWEEP_DIR.glob("*.jpg")) + sorted(SWEEP_DIR.glob("*.JPG"))
    print(f"\n{len(shot_paths)} shots in sweep 1")
    if not shot_paths:
        print("No shots found!")
        return 1

    # Quick sanity: load first shot, check feature centres
    first_img = np.asarray(Image.open(shot_paths[0]).convert("RGB"))
    H, W = first_img.shape[:2]
    print(f"  Shot image shape: {first_img.shape}")

    usable_features = []
    for f in top_features:
        u_mid = (f["bbox_uv"][0] + f["bbox_uv"][2]) / 2
        v_mid = (f["bbox_uv"][1] + f["bbox_uv"][3]) / 2
        cx, cy = die_uv_to_sweep_image(f["col_label"], f["row_label"],
                                         u_mid, v_mid, sweep_affine, atlas)
        inside = 0 < cx < W and 0 < cy < H
        print(f"  {f['die_label']} centre in sweep1: ({cx:.0f}, {cy:.0f}) {'✓' if inside else '✗ off-image'}")
        if inside:
            usable_features.append(f)

    if not usable_features:
        print("\nNone of the top features land inside sweep 1's image. Falling back to all features.")
        for f in features:
            u_mid = (f["bbox_uv"][0] + f["bbox_uv"][2]) / 2
            v_mid = (f["bbox_uv"][1] + f["bbox_uv"][3]) / 2
            cx, cy = die_uv_to_sweep_image(f["col_label"], f["row_label"],
                                             u_mid, v_mid, sweep_affine, atlas)
            if 0 < cx < W and 0 < cy < H:
                usable_features.append(f)
                if len(usable_features) >= 5:
                    break
        print(f"Selected {len(usable_features)} usable features")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    sweep_scale = sweep_affine["scale"]
    fig, ax = plt.subplots(figsize=(14, 7))

    results = {}
    for f in usable_features:
        pitch_u_sweep = f["pitch_u_atlas"] * sweep_scale if f["pitch_u_atlas"] else None
        pitch_v_sweep = f["pitch_v_atlas"] * sweep_scale if f["pitch_v_atlas"] else None
        print(f"\n=== {f['die_label']} ===")
        print(f"  atlas pitch (u, v) = ({f['pitch_u_atlas']}, {f['pitch_v_atlas']}) "
              f"→ sweep pitch ({pitch_u_sweep:.1f}, {pitch_v_sweep:.1f}) px")
        amps = []
        for idx, shot_path in enumerate(shot_paths):
            try:
                img = np.asarray(Image.open(shot_path).convert("RGB"))
                roi, _ = extract_feature_roi(img, f["bbox_uv"], f["col_label"],
                                              f["row_label"], sweep_affine, atlas)
                if roi is None:
                    amps.append(None)
                    continue
                amp = pad_fft_amplitude(roi, pitch_u_sweep, pitch_v_sweep)
                amps.append(amp)
            except Exception as e:
                print(f"  shot {idx}: error {e}")
                amps.append(None)
        valid = [(i, a) for i, a in enumerate(amps) if a is not None]
        if valid:
            argmax_idx, argmax_amp = max(valid, key=lambda x: x[1])
            print(f"  Argmax shot: {argmax_idx} (amp={argmax_amp:.4f})")
            print(f"  LSF reference:  shot {LSF_ARGMAX_SHOT}, "
                  f"amp={amps[LSF_ARGMAX_SHOT] if amps[LSF_ARGMAX_SHOT] else 'None'}")
            print(f"  POC B reference: shot {POC_B_ARGMAX_SHOT}, "
                  f"amp={amps[POC_B_ARGMAX_SHOT] if amps[POC_B_ARGMAX_SHOT] else 'None'}")
            results[f["die_label"]] = {
                "feature": f,
                "amps": amps,
                "argmax_shot": argmax_idx,
                "argmax_amp": argmax_amp,
                "lsf_shot_amp": amps[LSF_ARGMAX_SHOT],
                "pocb_shot_amp": amps[POC_B_ARGMAX_SHOT],
            }
            xs, ys = zip(*valid)
            ax.plot(xs, ys, label=f"{f['die_label']} (pitch_atlas u={f['pitch_u_atlas']:.0f}, v={f['pitch_v_atlas']:.0f})")

    ax.axvline(LSF_ARGMAX_SHOT, color="green", lw=1, ls="--", alpha=0.6,
               label=f"LSF argmax (shot {LSF_ARGMAX_SHOT})")
    ax.axvline(POC_B_ARGMAX_SHOT, color="red", lw=1, ls="--", alpha=0.6,
               label=f"POC B argmax (shot {POC_B_ARGMAX_SHOT})")
    ax.set_xlabel("Shot index")
    ax.set_ylabel("Pad-FFT amplitude (atlas-anchored)")
    ax.set_title(f"{SWEEP_NAME}: per-shot pad-FFT at atlas-anchored bond-pad regions")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out_png = OUT_DIR / f"{SWEEP_NAME}_atlas_anchored_pad_fft.png"
    fig.savefig(out_png, dpi=110)
    plt.close(fig)
    print(f"\nSaved plot: {out_png}")

    out_json = OUT_DIR / f"{SWEEP_NAME}_atlas_anchored_pad_fft.json"
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2,
                  default=lambda o: o.tolist() if hasattr(o, "tolist") else (
                      float(o) if hasattr(o, "__float__") and not isinstance(o, str) else str(o)))
    print(f"Saved results: {out_json}")

    print(f"\n=== Summary ===")
    print(f"{'feature':<14} {'argmax':<8} {'LSF gap':<10} {'POC B gap':<10}")
    for die_label, r in results.items():
        gap_lsf = r["argmax_shot"] - LSF_ARGMAX_SHOT
        gap_pocb = r["argmax_shot"] - POC_B_ARGMAX_SHOT
        print(f"{die_label:<14} {r['argmax_shot']:<8} {gap_lsf:+d} shots  {gap_pocb:+d} shots")


if __name__ == "__main__":
    sys.exit(main())
