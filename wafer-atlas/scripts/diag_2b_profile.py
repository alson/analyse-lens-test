"""For the AF200 6B two-pad die, dump the perpendicular intensity profile across
each candidate pad edge (top/bottom of each pad), over a WIDE window, so we can SEE
where the clean asymptote / nearest competing structure is, and measure true
clearance. This validates the isolation gate against the visual evidence that the
'pad-bbox edge' is often a narrow trench, not the open-field step."""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
import cv2, numpy as np
HERE = Path(__file__).resolve().parent; WA = HERE.parent; ROOT = WA.parent
sys.path.insert(0, str(ROOT / "tile-sharpness" / "src"))
from tile_sharpness.methods import pad_long_edge as ple
from tile_sharpness.methods.lsf import Segment
def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
reg_auto=_load("reg_auto")
OUTDIR=HERE/"diag_2b_padedge_out"; OUTDIR.mkdir(exist_ok=True)
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
jp = RAW/"Nikon AF Micro-Nikkor 200mm f_4D IF-ED"/"1_1"/"F8"/"00267|Nikon AF Micro-Nikkor 200mm f_4D IF-ED|1_1|200.0 mm|F8|alm-20260129-161423-267.jpg"
g=cv2.imread(str(jp),cv2.IMREAD_GRAYSCALE).astype(np.float32)
blk=(2095,4362,3363,5504)
pads=ple.find_bright_pad(g,blk)
print("pads:",pads)

def perp_profile(seg, side, pad, half=80):
    """Average intensity vs signed perpendicular distance (px), +d = away from pad
    on the open side, -d = into the pad."""
    L=seg.length_px
    ux,uy=(seg.x1-seg.x0)/L,(seg.y1-seg.y0)/L
    perpx,perpy=-uy,ux
    pad_sign=+1.0 if side=="top" else -1.0   # +perp roughly +y; pad is below for top
    H,W=g.shape
    ds=np.arange(-half,half,0.5)
    prof=[]
    for d in ds:
        vals=[]
        for t in np.linspace(0.2*L,0.8*L,40):
            cx=seg.x0+ux*t - pad_sign*perpx*d   # +d -> open side
            cy=seg.y0+uy*t - pad_sign*perpy*d
            xi,yi=int(round(cx)),int(round(cy))
            if 0<=xi<W and 0<=yi<H: vals.append(g[yi,xi])
        prof.append(np.mean(vals) if vals else np.nan)
    return ds,np.array(prof)

for pi,pad in enumerate(pads[:2]):
    for side in ("top","bottom"):
        res=ple.refine_pad_hedge(g,pad,side=side)
        if res is None:
            print(f"pad{pi} {side}: refine FAIL"); continue
        seg,off=res
        ds,prof=perp_profile(seg,side,pad,half=80)
        s="  ".join(f"{int(d):+3d}:{int(v)}" for d,v in zip(ds,prof) if abs(d)<=72 and abs(d)%6<0.5)
        print(f"pad{pi} {side} off={off:.1f} (open=+d, pad=-d):")
        print("   ",s)

# Also: scan the WHOLE block's row-mean profile to locate the widest open dark band
bx0,by0,bx1,by1=blk
# use the central left region (where the pads' clean cores are) x in [pad left .. +250]
xc0=min(p[0] for p in pads[:2]); xc1=xc0+260
strip=g[by0:by1, xc0:xc1]
rowmean=strip.mean(axis=1)
print("\nROW-MEAN profile (y from block top), looking for the widest open band:")
# print every 8 rows
for i in range(0,len(rowmean),16):
    bar="#"*int(rowmean[i]/8)
    print(f"  y={by0+i:5d} {int(rowmean[i]):3d} {bar}")
