"""Locate the 4D dark-bar edges precisely (sub-pixel via intensity), build a
Segment along the LONGEST (vertical) edge, and dump the geometry + a marked crop.

The atlas slanted_edge bbox gives the bar's approximate location; we refine to the
actual dark rectangle by thresholding, fit a straight line to the left & right
vertical edge points (one edge point per row = the steepest gradient column), and
return the longest clean vertical edge as a full-image Segment.
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
SE_BBOX = ATLAS["die_types"]["(0, 3)"]["feature_inventory"]["slanted_edge"][0]["bbox_uv"]
OUT = WA / "out" / "longedge_diag"
OUT.mkdir(parents=True, exist_ok=True)


def die_uv_to_img(col, row, u, v, p):
    if "k1" in p:
        return reg_auto.grid_xy_distorted(col + u, row + v, p)
    return reg_auto.af.grid_xy(col + u, row + v, p, ATLAS)


def find_bars(p):
    u0, v0, u1, v1 = SE_BBOX
    out = []
    for col in range(0, 11):
        for row in range(0, 6):
            if (col % 4, row % 4) != (0, 3):
                continue
            corners = [die_uv_to_img(col, row, u, v, p)
                       for (u, v) in [(u0, v0), (u0, v1), (u1, v0), (u1, v1)]]
            xs = [c[0] for c in corners]; ys = [c[1] for c in corners]
            m = 90
            if m < min(xs) and max(xs) < IMAGE_W - m and m < min(ys) and max(ys) < IMAGE_H - m:
                out.append((col, row, min(xs), min(ys), max(xs), max(ys)))
    return out


def refine_vertical_edge(g, x0, y0, x1, y1, side="left"):
    """Within the bbox (+pad), find the dark bar and return a Segment along one
    vertical edge fit to sub-pixel gradient peaks (one per row)."""
    pad = 35
    gx0, gy0 = max(0, int(x0 - pad)), max(0, int(y0 - pad))
    gx1, gy1 = min(IMAGE_W, int(x1 + pad)), min(IMAGE_H, int(y1 + pad))
    patch = g[gy0:gy1, gx0:gx1].astype(np.float32)
    ph, pw = patch.shape
    # column profile -> the bar is the dark central band
    colmean = patch.mean(axis=0)
    thr = (colmean.max() + colmean.min()) / 2.0
    dark = np.where(colmean < thr)[0]
    if dark.size < 5:
        return None
    bxl, bxr = int(dark.min()), int(dark.max())   # bar horizontal extent (local)
    # for each row, the left edge = steepest +gradient near bxl; right = steepest -grad near bxr
    pts = []
    for ry in range(ph):
        row = patch[ry]
        if side == "left":
            lo, hi = max(0, bxl - 8), min(pw - 1, bxl + 8)
            seg = row[lo:hi + 1]
            gr = np.gradient(seg)          # falling bg->dark => negative
            k = int(np.argmin(gr))
        else:
            lo, hi = max(0, bxr - 8), min(pw - 1, bxr + 8)
            seg = row[lo:hi + 1]
            gr = np.gradient(seg)          # rising dark->bg => positive
            k = int(np.argmax(gr))
        if 1 <= k <= len(seg) - 2:
            # parabolic sub-pixel on |gradient|
            ag = np.abs(gr)
            denom = (ag[k - 1] - 2 * ag[k] + ag[k + 1])
            off = 0.5 * (ag[k - 1] - ag[k + 1]) / denom if denom != 0 else 0.0
            pts.append((lo + k + off + gx0, ry + gy0))
    if len(pts) < 20:
        return None
    pts = np.array(pts)
    # robust line fit (x as function of y, near-vertical)
    ys = pts[:, 1]; xs = pts[:, 0]
    A = np.polyfit(ys, xs, 1)
    resid = xs - np.polyval(A, ys)
    keep = np.abs(resid) < 2.5 * (np.std(resid) + 1e-6)
    ys, xs = ys[keep], xs[keep]
    if ys.size < 20:
        return None
    A = np.polyfit(ys, xs, 1)
    y_a, y_b = float(ys.min()), float(ys.max())
    seg = Segment(x0=float(np.polyval(A, y_a)), y0=y_a,
                  x1=float(np.polyval(A, y_b)), y1=y_b)
    off_axis = abs(np.degrees(np.arctan(A[0])))   # deg off vertical
    return seg, off_axis, (gx0, gy0, patch)


def main():
    cfg = ("AF200 1:1 F8", RAW / "Nikon AF Micro-Nikkor 200mm f_4D IF-ED" / "1_1" / "F8")
    jpgs = sorted(cfg[1].glob("*.jpg"))
    aff = acm.register(jpgs)
    M = aff["scale"] / acm.M_ANCHOR_SCALE
    print(f"{cfg[0]} M={M:.3f} rmse={aff['reg_fit_rmse_px']:.2f}")
    bars = find_bars(aff)
    for (col, row, x0, y0, x1, y1) in bars:
        cx, cy = int((x0 + x1) / 2), int((y0 + y1) / 2)
        # best focus at this bar
        best = (-1, None)
        for jp in jpgs:
            gg = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
            if gg is None: continue
            lv = acm.roi_lapvar(gg, cx, cy, half=90)
            if lv > best[0]: best = (lv, gg)
        g = best[1]
        for side in ("left", "right"):
            r = refine_vertical_edge(g, x0, y0, x1, y1, side=side)
            if r is None:
                print(f"  die(c{col},r{row}) {side}: no edge"); continue
            seg, off, (ox, oy, patch) = r
            print(f"  die(c{col},r{row}) {side}: len={seg.length_px:.0f}px off-vert={off:.2f}deg "
                  f"seg=({seg.x0:.1f},{seg.y0:.1f})->({seg.x1:.1f},{seg.y1:.1f})")
            # marked crop
            vis = cv2.cvtColor(patch.astype(np.uint8), cv2.COLOR_GRAY2BGR)
            cv2.line(vis, (int(seg.x0 - ox), int(seg.y0 - oy)),
                     (int(seg.x1 - ox), int(seg.y1 - oy)), (0, 0, 255), 1)
            cv2.imwrite(str(OUT / f"4dbar_c{col}r{row}_{side}.png"), vis)


if __name__ == "__main__":
    main()
