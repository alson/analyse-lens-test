"""Test whether the length->lower-MTF50 effect is straight-line-model smear: build
the super-resolved ESF by binning each row relative to a SMOOTH (robust low-order
polynomial) edge centroid instead of a single straight line. If sigma then stays
~constant vs length, the smear was the straight-line assumption (detection scatter
+ bow), and a long edge IS usable once properly centred."""
from __future__ import annotations
import importlib.util, sys, json
from pathlib import Path
import cv2, numpy as np
from scipy.optimize import curve_fit
from scipy.special import erf
WA = Path(__file__).resolve().parent
TS = WA.parent.parent / "tile-sharpness"
sys.path.insert(0, str(TS / "src"))
from tile_sharpness.methods import slanted_edge as SE
from tile_sharpness.methods.long_edge import _subpixel_peak
_s = importlib.util.spec_from_file_location("reg_auto", WA / "reg_auto.py")
reg_auto = importlib.util.module_from_spec(_s); _s.loader.exec_module(reg_auto)
_a = importlib.util.spec_from_file_location("acm", TS / "scripts" / "atlas_corner_mtf.py")
acm = importlib.util.module_from_spec(_a); _a.loader.exec_module(acm)
ATLAS = json.load(open(WA.parent / "atlas.json"))
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
SE_BBOX = ATLAS["die_types"]["(0, 3)"]["feature_inventory"]["slanted_edge"][0]["bbox_uv"]
IMAGE_W, IMAGE_H = 8256, 5504
MTF50 = SE._MTF50_PER_INV_SIGMA

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

def recentred_esf(patch, bxl, poly_deg=2, half=12, bins_per_px=4.0, robust_iter=2):
    """Per-row edge centroid via gradient peak, robust poly fit -> bin all pixels by
    (x - edge_curve(y))."""
    ph,pw=patch.shape
    xs=[]; ys=[]
    for ry in range(ph):
        lo,hi=max(0,bxl-8),min(pw-1,bxl+8); sg=patch[ry,lo:hi+1]; gr=np.gradient(sg)
        k=int(np.argmin(gr))
        if 1<=k<=len(sg)-2: xs.append(lo+k+_subpixel_peak(np.abs(gr),k)); ys.append(ry)
    xs=np.array(xs,float); ys=np.array(ys,float)
    if len(xs)<10: return None
    A=np.polyfit(ys,xs,poly_deg)
    for _ in range(robust_iter):
        r=xs-np.polyval(A,ys); keep=np.abs(r)<2.0*(np.std(r)+1e-6)
        if keep.sum()<10: break
        A=np.polyfit(ys[keep],xs[keep],poly_deg)
    # bin every pixel within +-half of the edge curve
    yy,xx=np.mgrid[0:ph,0:pw]
    dist=xx-np.polyval(A,yy)
    keep=np.abs(dist)<=half
    d=dist[keep]; v=patch[keep].astype(float)
    nb=int(round(2*half*bins_per_px)); edges=np.linspace(-half,half,nb+1)
    idx=np.clip(np.digitize(d,edges)-1,0,nb-1)
    sums=np.bincount(idx,weights=v,minlength=nb); cnts=np.bincount(idx,minlength=nb)
    good=cnts>=3; centres=0.5*(edges[:-1]+edges[1:])
    return centres[good], sums[good]/cnts[good]

def fit_sigma(c,e):
    a0=(e[-1]-e[0])/2; b0=float(np.mean(e)); d0=float(c[int(np.argmax(np.abs(np.gradient(e))))])
    sp=float(e.max()-e.min())
    try:
        p,_=curve_fit(lambda d,a,b,d0,s:b+a*erf((d-d0)/(s*np.sqrt(2))),c,e,
                      p0=[a0,b0,d0,1.5],bounds=([-3*sp,e.min()-sp,c.min(),0.30],[3*sp,e.max()+sp,c.max(),30]),maxfev=10000)
        return abs(p[3])
    except Exception: return None

d=RAW/"Nikon AF Micro-Nikkor 200mm f_4D IF-ED"/"1_1"/"F8"
jpgs=sorted(d.glob("*.jpg")); aff=acm.register(jpgs); bars=find_bars(aff); col,row,bb=bars[0]
cx,cy=(bb[0]+bb[2])/2,(bb[1]+bb[3])/2
best=(-1,None)
for jp in jpgs:
    g=cv2.imread(str(jp),cv2.IMREAD_GRAYSCALE)
    if g is None: continue
    lv=acm.roi_lapvar(g,int(cx),int(cy),half=90)
    if lv>best[0]: best=(lv,g)
g=best[1].astype(np.float32)
pad=35
gx0,gy0=max(0,int(bb[0]-pad)),max(0,int(bb[1]-pad))
fullpatch=g[gy0:min(IMAGE_H,int(bb[3]+pad)), gx0:min(IMAGE_W,int(bb[2]+pad))]
cm=fullpatch.mean(axis=0); thr=(cm.max()+cm.min())/2; bxl=int(np.where(cm<thr)[0].min())
print("recentred (per-row poly) ESF, left edge:")
print(" rows  deg1_sigma deg1_mtf  deg2_sigma deg2_mtf  deg3_sigma deg3_mtf")
for nrows in [30,50,80,120,180,250,fullpatch.shape[0]]:
    r0=(fullpatch.shape[0]-nrows)//2
    sub=fullpatch[max(0,r0):r0+nrows]
    line=[]
    for deg in (1,2,3):
        out=recentred_esf(sub,bxl,poly_deg=deg)
        if out is None: line.append("  --   --  "); continue
        s=fit_sigma(*out); line.append(f"{s:7.3f} {MTF50/s:.4f}" if s else "  fail   ")
    print(f" {nrows:>4}  "+ "  ".join(line))
