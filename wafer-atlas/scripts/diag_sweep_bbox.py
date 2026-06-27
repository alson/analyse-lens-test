"""Diagnostic for Task #1: project every candidate 4D-bar instance into each
sweep's frame, report in-FOV / distance-from-centre, and render the actual ROI
crop (with the LSF Segment overlaid) for a spread of shots so we can see whether
the bar is in frame and whether its position drifts under defocus.

Outputs PNGs to out/diag_2026_06/.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

# Reuse the exact projection used by the production script.
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "task15", Path(__file__).parent / "task15_4d_bar_lsf_all_sweeps.py")
task15 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(task15)

A = Path(__file__).parent.parent
OUT = A / "out" / "diag_2026_06"
OUT.mkdir(parents=True, exist_ok=True)

atlas = json.load(open(A / "atlas.json"))
anchors = json.load(open(A / "out" / "sweep_anchors" / "anchor_fit_params.json"))

IMAGE_W, IMAGE_H = 8256, 5504
bar = atlas["die_types"]["(0, 3)"]["feature_inventory"]["slanted_edge"][0]
u_min, v_min, u_max, v_max = bar["bbox_uv"]


def candidate_table(sweep_name):
    aff = anchors[sweep_name]
    print(f"\n{'='*70}\n{sweep_name}  θ={aff['theta_deg']:.3f}° scale={aff['scale']:.4f} "
          f"rmse={aff['rmse_px']:.1f}px\n{'='*70}")
    u_mid, v_mid = (u_min+u_max)/2, (v_min+v_max)/2
    rows = []
    for col in [0, 4, 8]:
        cx, cy = task15.die_uv_to_sweep_image(col, 3, u_mid, v_mid, aff, atlas)
        corners = [task15.die_uv_to_sweep_image(col, 3, u, v, aff, atlas)
                   for (u, v) in [(u_min, v_min), (u_min, v_max), (u_max, v_min), (u_max, v_max)]]
        xs = [c[0] for c in corners]; ys = [c[1] for c in corners]
        margin = 100
        in_fov_centre = (margin < cx < IMAGE_W-margin) and (margin < cy < IMAGE_H-margin)
        bbox_fully_in = (min(xs) >= 0 and max(xs) < IMAGE_W and min(ys) >= 0 and max(ys) < IMAGE_H)
        dist = np.hypot(cx-IMAGE_W/2, cy-IMAGE_H/2)
        rows.append(dict(col=col, cx=cx, cy=cy, dist=dist, in_fov_centre=in_fov_centre,
                         bbox_fully_in=bbox_fully_in,
                         bbox_xy=(min(xs), min(ys), max(xs), max(ys))))
        print(f"  col {col}D: centre=({cx:8.0f},{cy:8.0f}) dist={dist:7.0f}  "
              f"centre_in_fov={in_fov_centre}  bbox_fully_in={bbox_fully_in}  "
              f"bbox=({min(xs):.0f},{min(ys):.0f})-({max(xs):.0f},{max(ys):.0f})")
    chosen = task15.pick_best_4d_instance(atlas, aff)
    print(f"  -> pick_best_4d_instance: col {chosen['col_label']}D "
          f"(dist {chosen['dist_from_centre']:.0f})" if chosen else "  -> NONE in FOV")
    return aff, rows, chosen


def render_rois(sweep_cfg, aff, col_label, tag, shot_fracs=(0.0, 0.25, 0.5, 0.75, 1.0)):
    """Render ROI crops at fractional positions through the sweep."""
    row_label = 3
    u_centerline = (u_min+u_max)/2
    x_bottom, y_bottom = task15.die_uv_to_sweep_image(col_label, row_label, u_centerline, v_min, aff, atlas)
    x_top, y_top = task15.die_uv_to_sweep_image(col_label, row_label, u_centerline, v_max, aff, atlas)
    bar_width_px = (u_max-u_min)*aff["scale"]*atlas["die_pitch_px_in_0129"]["d_col"][col_label % 4]
    corners = [task15.die_uv_to_sweep_image(col_label, row_label, u, v, aff, atlas)
               for (u, v) in [(u_min, v_min), (u_min, v_max), (u_max, v_min), (u_max, v_max)]]
    xs = [c[0] for c in corners]; ys = [c[1] for c in corners]
    margin_px = max(40, int(bar_width_px*1.5))
    roi_x_lo = max(0, int(min(xs)-margin_px)); roi_x_hi = int(max(xs)+margin_px)
    roi_y_lo = max(0, int(min(ys)-margin_px)); roi_y_hi = int(max(ys)+margin_px)

    shot_paths = sorted(sweep_cfg["dir"].glob("*.jpg")) + sorted(sweep_cfg["dir"].glob("*.JPG"))
    n = len(shot_paths)
    idxs = [min(n-1, int(round(f*(n-1)))) for f in shot_fracs]
    fig, axes = plt.subplots(1, len(idxs), figsize=(4*len(idxs), 4.5), squeeze=False)
    for ax, idx in zip(axes[0], idxs):
        img = np.asarray(Image.open(shot_paths[idx]).convert("L"))
        roi = img[roi_y_lo:min(img.shape[0], roi_y_hi), roi_x_lo:min(img.shape[1], roi_x_hi)]
        ax.imshow(roi, cmap="gray", vmin=0, vmax=255)
        ax.plot([x_bottom-roi_x_lo, x_top-roi_x_lo], [y_bottom-roi_y_lo, y_top-roi_y_lo],
                "r-", lw=1, alpha=0.8)
        ax.set_title(f"shot {idx}", fontsize=9)
        ax.axis("off")
    fig.suptitle(f"{sweep_cfg['name']} ROI via col {col_label}D  bar~{bar_width_px:.0f}px wide  "
                 f"roi=({roi_x_lo},{roi_y_lo})-({roi_x_hi},{roi_y_hi})", fontsize=10)
    fig.tight_layout()
    p = OUT / f"{sweep_cfg['name']}_roi_{tag}.png"
    fig.savefig(p, dpi=100); plt.close(fig)
    print(f"  rendered {p.name}")
    return dict(roi=(roi_x_lo, roi_y_lo, roi_x_hi, roi_y_hi), bar_width_px=bar_width_px, n_shots=n)


if __name__ == "__main__":
    cfgs = {c["name"]: c for c in task15.SWEEPS}
    for name in ["sweep2_M1.0", "sweep4_newer_rig"]:
        aff, rows, chosen = candidate_table(name)
        cfg = cfgs[name]
        # render for the chosen instance AND for col 4 (the geometric centre instance) if different
        cols_to_render = sorted({chosen["col_label"] if chosen else 4, 4})
        for col in cols_to_render:
            # only render cols that have a centre roughly in-frame-ish (bbox overlaps)
            render_rois(cfg, aff, col, tag=f"col{col}")
