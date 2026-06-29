"""Is the length->lower-MTF50 effect straightness-smear? Dump per-row edge-position
residual to the straight-line fit (the smear source), and the erf sigma vs length."""
from __future__ import annotations
import importlib.util, sys, json
from pathlib import Path
import cv2, numpy as np
WA = Path(__file__).resolve().parent
TS = WA.parent.parent / "tile-sharpness"
sys.path.insert(0, str(TS / "src"))
from tile_sharpness.methods.long_edge import refine_bar_edge, subsegment, _subpixel_peak
from tile_sharpness.methods import slanted_edge as SE
_s = importlib.util.spec_from_file_location("reg_auto", WA / "reg_auto.py")
reg_auto = importlib.util.module_from_spec(_s); _s.loader.exec_module(reg_auto)
_a = importlib.util.spec_from_file_location("acm", TS / "scripts" / "atlas_corner_mtf.py")
acm = importlib.util.module_from_spec(_a); _a.loader.exec_module(acm)
ATLAS = json.load(open(WA.parent / "atlas.json"))
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
SE_BBOX = ATLAS["die_types"]["(0, 3)"]["feature_inventory"]["slanted_edge"][0]["bbox_uv"]
IMAGE_W, IMAGE_H = 8256, 5504

def find_bars(p):
    u0,v0,u1,v1=SE_BBOX; out=[]
    for col in range(11):
        for row in range(6):
            if (col%4,row%4)!=(0,3): continue
            cs=[reg_auto.af.grid_xy(col+u,row+v,p,ATLAS) for u,v in [(u0,v0),(u0,v1),(u1,v0),(u1,v1)]]
            xs=[c[0] for c in cs]; ys=[c[1] for c in cs]; m=90
            if m<min(xs) and max(xs)<IMAGE_W-m and m<min(ys) and max(ys)<IMAGE_H-m:
                out.append((col,row,(min(xs),min(ys),max(xs),max(ys))))
    return out

d=RAW/"Nikon AF Micro-Nikkor 200mm f_4D IF-ED"/"1_1"/"F8"
jpgs=sorted(d.glob("*.jpg"))
aff=acm.register(jpgs); bars=find_bars(aff); col,row,bb=bars[0]
cx,cy=(bb[0]+bb[2])/2,(bb[1]+bb[3])/2
best=(-1,None)
for jp in jpgs:
    g=cv2.imread(str(jp),cv2.IMREAD_GRAYSCALE)
    if g is None: continue
    lv=acm.roi_lapvar(g,int(cx),int(cy),half=90)
    if lv>best[0]: best=(lv,g)
g=best[1].astype(np.float32)

# raw per-row edge positions (re-detect, before line fit) for the left edge
pad=35
gx0,gy0=max(0,int(bb[0]-pad)),max(0,int(bb[1]-pad))
gx1,gy1=min(IMAGE_W,int(bb[2]+pad)),min(IMAGE_H,int(bb[3]+pad))
patch=g[gy0:gy1,gx0:gx1]
colmean=patch.mean(axis=0); thr=(colmean.max()+colmean.min())/2
dark=np.where(colmean<thr)[0]; bxl=int(dark.min())
xs=[]; ys=[]
for ry in range(patch.shape[0]):
    rw=patch[ry]; lo,hi=max(0,bxl-8),min(patch.shape[1]-1,bxl+8)
    sg=rw[lo:hi+1]; gr=np.gradient(sg); k=int(np.argmin(gr))
    if 1<=k<=len(sg)-2:
        xs.append(lo+k+_subpixel_peak(np.abs(gr),k)); ys.append(ry)
xs=np.array(xs); ys=np.array(ys)
A=np.polyfit(ys,xs,1); resid=xs-np.polyval(A,ys)
print(f"raw edge points: n={len(xs)} slope={A[0]:+.4f}px/row  resid std={resid.std():.3f}px ptp={np.ptp(resid):.3f}px")
# quadratic fit -> bow?
A2=np.polyfit(ys,xs,2)
print(f"quadratic coef (bow) = {A2[0]:+.2e} px/row^2 ; over {len(ys)}rows that's {A2[0]*len(ys)**2:+.2f}px deflection")
# erf sigma vs length, on the untrimmed window
seg,off=refine_bar_edge(g,bb,side="left")
print("len  sigma_px  mtf50_erf_full  iso")
for Lreq in [30,50,80,120,180,250,999]:
    sub=subsegment(seg,Lreq)
    out=SE.superres_esf(g,sub,half_window_px=30,bins_per_px=4.0)
    if out is None: print(f"{Lreq} None"); continue
    c,e=out; m=SE._fit_wall(c,e)
    sigma=(SE._MTF50_PER_INV_SIGMA/m) if m else float('nan')
    iso=SE.mtf50_step_iso(g,sub,half_window_px=30)
    print(f"{Lreq:>4} {sigma:7.3f}   {m if m else 0:.4f}        {iso if iso else 0:.4f}")
