"""Diagnostic (2026-06-28): pad-edge MTF50 validation on the 3 known-ceiling configs.

Gate-passing pad edges only (single-step quality gate on the FULL super-res ESF:
rejects bright-trace ridges / troughs / noise / sigma-floor fits). Dumps the
trimmed ESF + a crop for every accepted edge so the reading can be eyeballed.

Make-or-break: do gate-passing pad edges read <= ceiling AND discriminate?
Set DIAG_CONFIGS=af200|sigma150|105vr6t (comma list) to subset; default all.
"""
from __future__ import annotations
import importlib.util, os, sys
from pathlib import Path
import cv2, numpy as np

WA = Path(__file__).resolve().parent
TS = WA.parent.parent / "tile-sharpness"
sys.path.insert(0, str(TS / "src"))
from tile_sharpness.methods.lsf import Segment, cross_section, lsf_mtf50
from tile_sharpness.methods.slanted_edge import (mtf50_step_erf, mtf50_step_iso,
                                                 superres_esf, _trim_to_dominant_step, _MTF50_PER_INV_SIGMA)
from tile_sharpness.methods import pad_edge as pe
from tile_sharpness import optics

_s = importlib.util.spec_from_file_location("acm", TS / "scripts" / "atlas_corner_mtf.py")
acm = importlib.util.module_from_spec(_s); _s.loader.exec_module(acm)
reg_auto = acm.reg_auto
ATLAS = reg_auto.ATLAS
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
CROPD = WA / "diag_padedge_crops"; CROPD.mkdir(exist_ok=True)

ALL = {
    "af200": ("AF200 1:1 F11", RAW / "Nikon AF Micro-Nikkor 200mm f_4D IF-ED" / "1_1" / "F11", 11.0),
    "sigma150": ("Sigma150 1:1 F8", RAW / "Sigma APO Macro 150mm F2.8 EX DG OS HSM" / "1_1" / "F8", 8.0),
    "105vr6t": ("105VR+6T F8", RAW / "NIKKOR Z MC 105mm f_2.8 VR S + 6T" / "1.4_1" / "F8", 8.0),
}
TARGETS = acm.TARGETS


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
    sel = os.environ.get("DIAG_CONFIGS")
    keys = sel.split(",") if sel else list(ALL)
    gate = lambda im, s: mtf50_step_erf(im, s, half_window_px=30) is not None
    for key in keys:
        label, d, n_set = ALL[key]
        jpgs = sorted(d.glob("*.jpg")) or sorted(d.glob("*.JPG"))
        if not jpgs:
            print(f"{label}: no jpgs", flush=True); continue
        aff = acm.register(jpgs)
        if aff is None:
            print(f"{label}: REG FAILED", flush=True); continue
        M = aff["scale"] / acm.M_ANCHOR_SCALE
        ceil = optics.diffraction_mtf50_sensor_lpmm(n_set * (1 + M)) / acm.LPMM_PER_CYPX
        print(f"\n=== {label}  M={M:.3f} ceiling={ceil:.3f} cy/px (rmse {aff['reg_fit_rmse_px']:.2f}) ===", flush=True)
        detimg = acm.decode(jpgs[len(jpgs)//2])
        picks = pe.pick_padedge_targets(aff, ATLAS, grid_xy, TARGETS, detimg, pad_px=25, accept=gate)
        scribes = acm.pick_scribes(aff)
        for name in TARGETS:
            if name not in picks:
                print(f"  {name:6}: NO gate-passing pad edge", flush=True); continue
            r, seg, off, L = picks[name]
            mx, my = (seg.x0+seg.x1)/2, (seg.y0+seg.y1)/2
            g = best_focus(jpgs, mx, my)
            gf = g.astype(np.float32)
            erf = mtf50_step_erf(gf, seg, half_window_px=30)
            iso = mtf50_step_iso(gf, seg, half_window_px=30)
            out = superres_esf(gf, seg, half_window_px=30)
            ct, et = _trim_to_dominant_step(*out) if out else (np.array([]), np.array([]))
            fl = lambda x: "OVER" if (x and x > ceil*1.02) else "ok  "
            f = lambda x: f"{x:.3f}" if x else "  -  "
            grv = "  -  "
            if name in scribes:
                _, _, gseg = scribes[name]
                go = lsf_mtf50(cross_section(gf, gseg, half_window_px=acm.HALF_WIN,
                                             samples_per_pixel=acm.SPP), combine="min")
                grv = f"{go:.3f}[{fl(go)}]" if go else "  -  "
            sig = (_MTF50_PER_INV_SIGMA/erf) if erf else None
            print(f"  {name:6}: die({r['col']},{r['row']}) len={L:.0f}px off={off:.1f} | "
                  f"padedge erf={f(erf)}[{fl(erf)}] (sig~{sig:.2f}px) iso={f(iso)} | groove_min={grv}"
                  if sig else
                  f"  {name:6}: die({r['col']},{r['row']}) len={L:.0f}px off={off:.1f} | "
                  f"padedge erf={f(erf)} iso={f(iso)} | groove_min={grv}", flush=True)
            if et.size:
                print("         trimESF:", " ".join(f"{y:.0f}" for y in et[::2]), flush=True)
            cs = 70; x0,y0 = int(mx-cs), int(my-cs)
            crop = g[max(0,y0):y0+2*cs, max(0,x0):x0+2*cs]
            cv2.imwrite(str(CROPD / f"{key}_{name}.png"), crop)


if __name__ == "__main__":
    main()
