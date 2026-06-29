"""Diagnostic (longedge task): for a registered sweep, locate the target LONG-edge
features in-frame and report their in-pixel edge lengths + save crops.

Targets (die type -> feature):
  (0,3) 4D  : slanted_edge bbox (the dark vertical bar) -> LONGEST edge = vertical
  (2,1) 2B  : experimental bbox  (two bright central rectangles)
  (2,2) 2C  : experimental bbox  (large cyan/uniform rectangle)
  (3,1) 3B  : bond_pads bboxes   (the magenta rectangles -- 3B has no experimental)

This is pure geometry + crop; no MTF. It tells us whether a LONG isolated edge is
in FOV for a given config and how many pixels long it is (the height hypothesis).
"""
from __future__ import annotations
import importlib.util, sys, json
from pathlib import Path
import cv2, numpy as np

WA = Path(__file__).resolve().parent
TS = WA.parent.parent / "tile-sharpness"
sys.path.insert(0, str(TS / "src"))
from tile_sharpness.methods.lsf import Segment

_s = importlib.util.spec_from_file_location("reg_auto", WA / "reg_auto.py")
reg_auto = importlib.util.module_from_spec(_s); _s.loader.exec_module(reg_auto)
_a = importlib.util.spec_from_file_location("acm", TS / "scripts" / "atlas_corner_mtf.py")
acm = importlib.util.module_from_spec(_a); _a.loader.exec_module(acm)

ATLAS = json.load(open(WA.parent / "atlas.json"))
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
IMAGE_W, IMAGE_H = 8256, 5504
OUT = WA / "out" / "longedge_diag"
OUT.mkdir(parents=True, exist_ok=True)

# (die_type, feature_inventory_key) for each named target
TARGETS = {
    "4D_bar":  ("(0, 3)", "slanted_edge"),
    "2B_rect": ("(2, 1)", "experimental"),
    "2C_rect": ("(2, 2)", "experimental"),
    "3B_rect": ("(3, 1)", "bond_pads"),
}


def die_uv_to_img(col, row, u, v, p):
    if "k1" in p:
        return reg_auto.grid_xy_distorted(col + u, row + v, p)
    return reg_auto.af.grid_xy(col + u, row + v, p, ATLAS)


def feature_bbox_img(col, row, bbox_uv, p):
    u0, v0, u1, v1 = bbox_uv
    corners = [die_uv_to_img(col, row, u, v, p)
               for (u, v) in [(u0, v0), (u0, v1), (u1, v0), (u1, v1)]]
    xs = [c[0] for c in corners]; ys = [c[1] for c in corners]
    return min(xs), min(ys), max(xs), max(ys)


def in_fov(x0, y0, x1, y1, m=80):
    return (m < x0 and x1 < IMAGE_W - m and m < y0 and y1 < IMAGE_H - m)


def find_target(typ, key, p):
    """Return list of (col,row,comp,bbox_img) for all in-FOV instances of feature."""
    feats = ATLAS["die_types"][typ].get("feature_inventory", {}).get(key, [])
    found = []
    for col in range(0, 11):
        for row in range(0, 6):
            if (col % 4, row % 4) != tuple(int(x) for x in typ.strip("()").split(",")):
                continue
            for ci, bp in enumerate(feats):
                bb = feature_bbox_img(col, row, bp["bbox_uv"], p)
                if in_fov(*bb):
                    found.append((col, row, ci, bb, bp["bbox_uv"]))
    return found


def best_focus(jpgs, mx, my):
    best = (-1.0, None)
    for jp in jpgs:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        lv = acm.roi_lapvar(g, int(mx), int(my), half=90)
        if lv > best[0]:
            best = (lv, g)
    return best[1]


def main(cfg_label, cfg_dir, n_set):
    jpgs = sorted(Path(cfg_dir).glob("*.jpg"))
    if not jpgs:
        print(f"{cfg_label}: no jpgs"); return
    aff = acm.register(jpgs)
    if aff is None:
        print(f"{cfg_label}: REG FAILED"); return
    M = aff["scale"] / acm.M_ANCHOR_SCALE
    print(f"\n=== {cfg_label}  M={M:.3f}  rmse={aff['reg_fit_rmse_px']:.2f} ===")
    for name, (typ, key) in TARGETS.items():
        found = find_target(typ, key, aff)
        if not found:
            print(f"  {name:8s}: not in FOV")
            continue
        for (col, row, ci, bb, uv) in found:
            x0, y0, x1, y1 = (int(round(v)) for v in bb)
            w, h = x1 - x0, y1 - y0
            # the LONGEST edge of an axis-ish rectangle ~ the longer side
            long_edge = max(w, h)
            print(f"  {name:8s} die(c{col},r{row}) comp{ci} uv={uv} "
                  f"bbox=({x0},{y0},{x1},{y1}) {w}x{h}px  longedge~{long_edge}px")
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            g = best_focus(jpgs, cx, cy)
            pad = 40
            crop = g[max(0, y0 - pad):min(IMAGE_H, y1 + pad),
                     max(0, x0 - pad):min(IMAGE_W, x1 + pad)]
            fn = OUT / f"{cfg_label.replace(' ', '_').replace('/', '_')}_{name}_c{col}r{row}_{ci}.png"
            cv2.imwrite(str(fn), crop)


if __name__ == "__main__":
    CONFIGS = [
        ("AF200 1:1 F8", RAW / "Nikon AF Micro-Nikkor 200mm f_4D IF-ED" / "1_1" / "F8", 8.0),
    ]
    for lab, d, n in CONFIGS:
        main(lab, d, n)
