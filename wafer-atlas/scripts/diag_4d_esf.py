"""Dump the super-resolved ESF + erf/iso fits for the 4D bar left edge at several
edge lengths, to diagnose why mtf50_step_erf is erratic vs length."""
from __future__ import annotations
import importlib.util, sys, json
from pathlib import Path
import cv2, numpy as np

WA = Path(__file__).resolve().parent
TS = WA.parent.parent / "tile-sharpness"
sys.path.insert(0, str(TS / "src"))
from tile_sharpness.methods.lsf import Segment
from tile_sharpness.methods.long_edge import refine_bar_edge, subsegment
from tile_sharpness.methods import slanted_edge as SE

_s = importlib.util.spec_from_file_location("reg_auto", WA / "reg_auto.py")
reg_auto = importlib.util.module_from_spec(_s); _s.loader.exec_module(reg_auto)
_a = importlib.util.spec_from_file_location("acm", TS / "scripts" / "atlas_corner_mtf.py")
acm = importlib.util.module_from_spec(_a); _a.loader.exec_module(acm)
ATLAS = json.load(open(WA.parent / "atlas.json"))
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
SE_BBOX = ATLAS["die_types"]["(0, 3)"]["feature_inventory"]["slanted_edge"][0]["bbox_uv"]
IMAGE_W, IMAGE_H = 8256, 5504


def fmt(x):
    return f"{x:.4f}" if x else "None"


def find_bars(p):
    u0, v0, u1, v1 = SE_BBOX
    out = []
    for col in range(0, 11):
        for row in range(0, 6):
            if (col % 4, row % 4) != (0, 3): continue
            cs = [reg_auto.af.grid_xy(col+u, row+v, p, ATLAS) for u,v in [(u0,v0),(u0,v1),(u1,v0),(u1,v1)]]
            xs=[c[0] for c in cs]; ys=[c[1] for c in cs]; m=90
            if m<min(xs) and max(xs)<IMAGE_W-m and m<min(ys) and max(ys)<IMAGE_H-m:
                out.append((col,row,(min(xs),min(ys),max(xs),max(ys))))
    return out


d = RAW / "Nikon AF Micro-Nikkor 200mm f_4D IF-ED" / "1_1" / "F8"
jpgs = sorted(d.glob("*.jpg"))
aff = acm.register(jpgs)
M = aff["scale"]/acm.M_ANCHOR_SCALE
bars = find_bars(aff)
col,row,bb = bars[0]
cx,cy=(bb[0]+bb[2])/2,(bb[1]+bb[3])/2
best=(-1,None)
for jp in jpgs:
    g=cv2.imread(str(jp),cv2.IMREAD_GRAYSCALE)
    if g is None: continue
    lv=acm.roi_lapvar(g,int(cx),int(cy),half=90)
    if lv>best[0]: best=(lv,g)
g=best[1].astype(np.float32)
seg,off = refine_bar_edge(g, bb, side="left")
print(f"M={M:.3f} full_len={seg.length_px:.0f} off={off:.2f}deg")
for Lreq in [30,50,80,120,180,250,999]:
    sub=subsegment(seg,Lreq)
    out=SE.superres_esf(g,sub,half_window_px=30,bins_per_px=4.0)
    if out is None:
        print(f" L={Lreq:>4} ({sub.length_px:.0f}px): ESF None"); continue
    c,e=out
    gate = SE._step_quality_ok(c,e)
    ct,et = SE._trim_to_dominant_step(c,e)
    m_full = SE._fit_wall(c,e)
    m_trim = SE._fit_wall(ct,et)
    m_step = SE.mtf50_step_erf(g,sub,half_window_px=30)
    m_iso = SE.mtf50_step_iso(g,sub,half_window_px=30)
    # ESF shape summary
    print(f" L={Lreq:>4} ({sub.length_px:5.0f}px) gate={gate} nbins={e.size} trimbins={et.size} "
          f"contrast={e[-1]-e[0]:+.0f} min/max=({e.min():.0f},{e.max():.0f}) "
          f"erf_full={fmt(m_full)} erf_trim={fmt(m_trim)} step_erf={fmt(m_step)} iso={fmt(m_iso)}")
