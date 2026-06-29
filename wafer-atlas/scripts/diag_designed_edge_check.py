"""Sanity: confirm the single-STEP estimator (mtf50_step_erf) reads the atlas's
DESIGNED slanted-edge feature (die (0,3), the POC's known-good TRUE edge) at <=
ceiling, ~0.10 cy/px — isolating the pad-edge over-read to the pad-array geometry,
NOT the estimator. Mirrors poc_true_edge_feature's feature-location logic."""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
import cv2, numpy as np

WA = Path(__file__).resolve().parent
TS = WA.parent.parent / "tile-sharpness"
sys.path.insert(0, str(TS / "src"))
from tile_sharpness.methods.lsf import Segment
from tile_sharpness.methods.slanted_edge import mtf50_step_erf, mtf50_erf, mtf50_step_iso
from tile_sharpness.methods.pad_edge import slanted_edge_candidates
from tile_sharpness import optics

_s = importlib.util.spec_from_file_location("acm", TS / "scripts" / "atlas_corner_mtf.py")
acm = importlib.util.module_from_spec(_s); _s.loader.exec_module(acm)
reg_auto = acm.reg_auto
ATLAS = reg_auto.ATLAS
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
IMAGE_W, IMAGE_H = 8256, 5504
SE_BBOX = [0.585, 0.447, 0.707, 0.682]   # die (0,3) slanted_edge uv bbox (POC)

CONFIGS = [
    ("AF200 1:1 F11", RAW / "Nikon AF Micro-Nikkor 200mm f_4D IF-ED" / "1_1" / "F11", 11.0),
    ("Sigma150 1:1 F8", RAW / "Sigma APO Macro 150mm F2.8 EX DG OS HSM" / "1_1" / "F8", 8.0),
    ("105VR+6T F8", RAW / "NIKKOR Z MC 105mm f_2.8 VR S + 6T" / "1.4_1" / "F8", 8.0),
]


def die_uv_to_img(col, row, u, v, p):
    return reg_auto.grid_xy_distorted(col + u, row + v, p) if "k1" in p else \
        reg_auto.af.grid_xy(col + u, row + v, p, ATLAS)


def find_se(p):
    u0, v0, u1, v1 = SE_BBOX
    for col in (0, 4, 8):
        corners = [die_uv_to_img(col, 3, u, v, p) for (u, v) in
                   [(u0, v0), (u0, v1), (u1, v0), (u1, v1)]]
        xs = [c[0] for c in corners]; ys = [c[1] for c in corners]; m = 80
        if (m < np.mean(xs) < IMAGE_W - m and m < np.mean(ys) < IMAGE_H - m
                and min(xs) > 0 and max(xs) < IMAGE_W and min(ys) > 0 and max(ys) < IMAGE_H):
            return (col, int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
    return None


def best_focus(jpgs, mx, my, half=90):
    best = (-1.0, None)
    for jp in jpgs:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None: continue
        lv = acm.roi_lapvar(g, mx, my, half=half)
        if lv > best[0]: best = (lv, g)
    return best[1]


def main():
    for label, d, n_set in CONFIGS:
        jpgs = sorted(d.glob("*.jpg"))
        aff = acm.register(jpgs)
        if aff is None: print(f"{label}: REG FAIL", flush=True); continue
        M = aff["scale"] / acm.M_ANCHOR_SCALE
        ceil = optics.diffraction_mtf50_sensor_lpmm(n_set*(1+M)) / acm.LPMM_PER_CYPX
        se = find_se(aff)
        if se is None: print(f"{label}: designed-edge NOT in FOV", flush=True); continue
        col, x0, y0, x1, y1 = se
        cx, cy = (x0+x1)//2, (y0+y1)//2
        g = best_focus(jpgs, cx, cy); pad = 30
        patch = g[max(0,y0-pad):y1+pad, max(0,x0-pad):x1+pad]
        cands = slanted_edge_candidates(patch.astype(np.uint8), max(0,x0-pad), max(0,y0-pad))
        gf = g.astype(np.float32)
        step = next((mtf50_step_erf(gf, s) for s,_,_ in cands if mtf50_step_erf(gf, s)), None)
        # also the groove-style two-wall read used by the POC
        seg0 = cands[0][0] if cands else None
        grv = mtf50_erf(gf, seg0, half_window_px=30, combine="min") if seg0 else None
        fl = lambda x: "OVER" if (x and x>ceil*1.02) else "ok"
        f = lambda x: f"{x:.3f}" if x else "  -  "
        print(f"{label} M={M:.3f} ceil={ceil:.3f}: designed-edge step_erf={f(step)}[{fl(step)}] "
              f"two-wall_min={f(grv)}[{fl(grv)}] ({len(cands)} cands)", flush=True)


if __name__ == "__main__":
    main()
