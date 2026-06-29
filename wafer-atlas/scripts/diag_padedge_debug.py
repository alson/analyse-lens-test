"""Debug the pad-edge over-read: dump the ESF, the detected edge geometry, and an
image crop for AF200 1:1 F11 centre + a couple of targets, to see whether the
0.625 (sigma-floor) readings are a real edge or a pipeline artifact (e.g. Hough
picking a pad-array boundary, super-res binning collapse, or specular glint)."""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
import cv2, numpy as np

WA = Path(__file__).resolve().parent
TS = WA.parent.parent / "tile-sharpness"
sys.path.insert(0, str(TS / "src"))
from tile_sharpness.methods.lsf import Segment, cross_section, lsf_mtf50
from tile_sharpness.methods.slanted_edge import (superres_esf, mtf50_step_erf, mtf50_step_iso,
                                                 _trim_to_dominant_step, _fit_wall, _MTF50_PER_INV_SIGMA)
from tile_sharpness.methods import pad_edge as pe
from tile_sharpness import optics

_s = importlib.util.spec_from_file_location("acm", TS / "scripts" / "atlas_corner_mtf.py")
acm = importlib.util.module_from_spec(_s); _s.loader.exec_module(acm)
reg_auto = acm.reg_auto
ATLAS = reg_auto.ATLAS
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")

CFG = ("AF200 1:1 F11", RAW / "Nikon AF Micro-Nikkor 200mm f_4D IF-ED" / "1_1" / "F11", 11.0)


def grid_xy(col, row, u, v, p):
    if "k1" in p:
        return reg_auto.grid_xy_distorted(col + u, row + v, p)
    return reg_auto.af.grid_xy(col + u, row + v, p, ATLAS)


def best_focus(jpgs, mx, my, half=90):
    best = (-1.0, None)
    for jp in jpgs:
        g = cv2.imread(str(jp), cv2.IMREAD_GRAYSCALE)
        if g is None: continue
        lv = acm.roi_lapvar(g, mx, my, half=half)
        if lv > best[0]: best = (lv, g)
    return best[1]


def main():
    label, d, n_set = CFG
    jpgs = sorted(d.glob("*.jpg"))
    aff = acm.register(jpgs)
    M = aff["scale"] / acm.M_ANCHOR_SCALE
    ceil = optics.diffraction_mtf50_sensor_lpmm(n_set * (1 + M)) / acm.LPMM_PER_CYPX
    print(f"{label} M={M:.3f} ceiling={ceil:.3f} cy/px")
    detimg = acm.decode(jpgs[len(jpgs)//2])
    picks = pe.pick_padedge_targets(aff, ATLAS, grid_xy, acm.TARGETS, detimg, pad_px=25)
    for name in ("centre", "BL"):
        if name not in picks:
            print(f"{name}: no pick"); continue
        r, seg, off, L = picks[name]
        mx, my = (seg.x0+seg.x1)/2, (seg.y0+seg.y1)/2
        g = best_focus(jpgs, mx, my)
        gf = g.astype(np.float32)
        out = superres_esf(gf, seg, half_window_px=30)
        c, e = out
        ct, et = _trim_to_dominant_step(c, e)
        sig_fit = mtf50_step_erf(gf, seg, half_window_px=30)
        print(f"\n--- {name} die({r['col']},{r['row']}) edge len={L:.0f} off={off:.1f}deg "
              f"seg=({seg.x0:.0f},{seg.y0:.0f})->({seg.x1:.0f},{seg.y1:.0f}) ---")
        print(f"  full ESF n={e.size} range {e.min():.1f}..{e.max():.1f}")
        print(f"  trimmed ESF n={ct.size} span {ct.min():.2f}..{ct.max():.2f} px range {et.min():.1f}..{et.max():.1f}")
        print(f"  step_erf={sig_fit:.4f} cy/px (sigma~{_MTF50_PER_INV_SIGMA/sig_fit:.3f} px)")
        # print the trimmed ESF values
        print("  trimmed ESF (d:val):", " ".join(f"{x:.1f}:{y:.0f}" for x,y in zip(ct[::2], et[::2])))
        # dump a small image crop around the edge centre for visual inspection
        cs = 60
        x0,y0 = int(mx-cs), int(my-cs)
        crop = g[max(0,y0):y0+2*cs, max(0,x0):x0+2*cs]
        outp = WA / f"diag_padedge_crop_{label.split()[0]}_{name}.png"
        cv2.imwrite(str(outp), crop)
        print(f"  saved crop {outp.name} ({crop.shape})")
        # also: what does the RAW pixel row across the edge look like (no super-res)?
        # sample a perpendicular line at the segment midpoint
        ux,uy = (seg.x1-seg.x0)/L,(seg.y1-seg.y0)/L; pxv,pyv = -uy,ux
        line = [g[int(my+pyv*t), int(mx+pxv*t)] for t in range(-15,16) if 0<=int(my+pyv*t)<g.shape[0] and 0<=int(mx+pxv*t)<g.shape[1]]
        print("  RAW perpendicular (1px steps):", " ".join(str(int(v)) for v in line))


if __name__ == "__main__":
    main()
