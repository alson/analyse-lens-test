"""POC (2026-06-28): test the user's groove-emboss hypothesis by measuring MTF50 on
the atlas's designated TRUE slanted-edge feature (die type (0,3), source 4D) instead
of the groove scribe. A groove wall is a lit/shadow emboss edge (asymmetric → the lit
wall over-reads); a designed slanted-edge target is a true reflectance edge and should
read <= the diffraction ceiling. Compares: groove-scribe (old + superres) vs the
true-edge feature, against the ceiling.
"""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
import cv2, numpy as np

WA = Path(__file__).resolve().parent
TS = WA.parent.parent / "tile-sharpness"
sys.path.insert(0, str(TS / "src"))
from tile_sharpness.methods.lsf import Segment, detect_scribe, cross_section, lsf_mtf50
from tile_sharpness.methods.slanted_edge import mtf50_erf, mtf50_iso, superres_esf
from tile_sharpness import optics
_s = importlib.util.spec_from_file_location("acm", TS / "scripts" / "atlas_corner_mtf.py")
acm = importlib.util.module_from_spec(_s); _s.loader.exec_module(acm)
reg_auto = acm.reg_auto
ATLAS = reg_auto.ATLAS

RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
IMAGE_W, IMAGE_H = 8256, 5504
SE_BBOX = [0.585, 0.447, 0.707, 0.682]   # die (0,3) slanted_edge uv bbox

CONFIGS = [
    ("AF200 1:1 F11 (anchor)", RAW / "Nikon AF Micro-Nikkor 200mm f_4D IF-ED" / "1_1" / "F11", 11.0),
    ("Sigma150 bare 1:1 F8",   RAW / "Sigma APO Macro 150mm F2.8 EX DG OS HSM" / "1_1" / "F8", 8.0),
    ("105VR+6T F8 (over-read)", RAW / "NIKKOR Z MC 105mm f_2.8 VR S + 6T" / "1.4_1" / "F8", 8.0),
]


def detect_edge_hough(patch):
    """Longest straight CONTRAST edge in the patch (not a dark line): Canny +
    probabilistic Hough, pick the longest segment. Returns a local Segment or None."""
    p = cv2.GaussianBlur(patch, (3, 3), 0)
    edges = cv2.Canny(p, 40, 120)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=40,
                            minLineLength=int(0.4 * min(patch.shape)), maxLineGap=8)
    if lines is None:
        return None
    x0, y0, x1, y1 = max((tuple(l[0]) for l in lines),
                         key=lambda l: np.hypot(l[2] - l[0], l[3] - l[1]))
    return Segment(x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1))


def die_uv_to_img(col, row, u, v, p):
    return reg_auto.grid_xy_distorted(col + u, row + v, p) if "k1" in p else \
        reg_auto.af.grid_xy(col + u, row + v, p, ATLAS)


def find_se_feature(p):
    """Locate the slanted_edge feature bbox in image coords if in-FOV."""
    u0, v0, u1, v1 = SE_BBOX
    for col in (0, 4, 8):
        for row in (3,):   # row D
            corners = [die_uv_to_img(col, row, u, v, p) for (u, v) in
                       [(u0, v0), (u0, v1), (u1, v0), (u1, v1)]]
            xs = [c[0] for c in corners]; ys = [c[1] for c in corners]
            m = 80
            if (m < np.mean(xs) < IMAGE_W - m and m < np.mean(ys) < IMAGE_H - m
                    and min(xs) > 0 and max(xs) < IMAGE_W and min(ys) > 0 and max(ys) < IMAGE_H):
                return (col, row, int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
    return None


def best_focus(jpgs, mx, my):
    best = (-1.0, None)
    for jp in jpgs:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        lv = acm.roi_lapvar(g, mx, my, half=90)
        if lv > best[0]:
            best = (lv, g)
    return best[1]


def main():
    for label, d, n_set in CONFIGS:
        jpgs = sorted(d.glob("*.jpg"))
        if not jpgs:
            print(f"{label}: no jpgs"); continue
        aff = acm.register(jpgs)
        if aff is None:
            print(f"{label}: REG FAILED"); continue
        M = aff["scale"] / acm.M_ANCHOR_SCALE
        ceil = optics.diffraction_mtf50_sensor_lpmm(n_set * (1 + M)) / 229.9
        print(f"\n{label}  M={M:.3f} ceiling={ceil:.3f} cy/px (rmse {aff['reg_fit_rmse_px']:.2f})")
        se = find_se_feature(aff)
        if se is None:
            print("  slanted_edge feature NOT in FOV");
        else:
            col, row, x0, y0, x1, y1 = se
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            g = best_focus(jpgs, cx, cy)
            pad = 30
            patch = g[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
            seg_local = detect_edge_hough(patch.astype(np.uint8))
            if seg_local is None:
                print(f"  SE feature @die({col},{row}) [{x1-x0}x{y1-y0}px]: no edge detected")
            else:
                ox, oy = max(0, x0 - pad), max(0, y0 - pad)
                seg = Segment(x0=seg_local.x0 + ox, y0=seg_local.y0 + oy,
                              x1=seg_local.x1 + ox, y1=seg_local.y1 + oy)
                gf = g.astype(np.float32)
                erf_min = mtf50_erf(gf, seg, half_window_px=30, combine="min")
                erf_mean = mtf50_erf(gf, seg, half_window_px=30, combine="mean")
                iso_min = mtf50_iso(gf, seg, half_window_px=30, combine="min")
                fl = lambda x: "OVER" if (x and x > ceil * 1.02) else "ok  "
                f = lambda x: f"{x:.3f}" if x else "  -  "
                print(f"  TRUE-EDGE feature @die({col},{row}) len={seg.length_px:.0f}px: "
                      f"erf_min={f(erf_min)}[{fl(erf_min)}] erf_mean={f(erf_mean)} iso_min={f(iso_min)}[{fl(iso_min)}]")
        # groove scribe at centre for comparison
        sc = acm.pick_scribes(aff)
        if "centre" in sc:
            mx, my, seg = sc["centre"]
            g = best_focus(jpgs, mx, my)
            gf = g.astype(np.float32)
            old = lsf_mtf50(cross_section(gf, seg, half_window_px=acm.HALF_WIN, samples_per_pixel=acm.SPP), combine="min")
            erf_min = mtf50_erf(gf, seg, combine="min")
            fl = lambda x: "OVER" if (x and x > ceil * 1.02) else "ok  "
            f = lambda x: f"{x:.3f}" if x else "  -  "
            print(f"  GROOVE scribe @centre: old_min={f(old)}[{fl(old)}] erf_min={f(erf_min)}[{fl(erf_min)}]")


if __name__ == "__main__":
    main()
