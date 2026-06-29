"""Debug: dump the uniformity mask + all components for the AF200 6B block, on the
best-focus frame, to see why the large upper pad is missed."""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
import cv2, numpy as np
HERE = Path(__file__).resolve().parent; WA = HERE.parent; ROOT = WA.parent
sys.path.insert(0, str(ROOT / "tile-sharpness" / "src"))
def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
reg_auto=_load("reg_auto")
OUTDIR=HERE/"diag_2b_padedge_out"; OUTDIR.mkdir(exist_ok=True)
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
jp = RAW/"Nikon AF Micro-Nikkor 200mm f_4D IF-ED"/"1_1"/"F8"/"00267|Nikon AF Micro-Nikkor 200mm f_4D IF-ED|1_1|200.0 mm|F8|alm-20260129-161423-267.jpg"
g=cv2.imread(str(jp),cv2.IMREAD_GRAYSCALE).astype(np.float32)
blk=(2095,4362,3363,5504)
bx0,by0,bx1,by1=blk
block=g[by0:by1,bx0:bx1]
bh,bw=block.shape
print("block shape",block.shape)
ws=max(5,(int(0.05*min(bh,bw))|1)); print("ws",ws)
blur=cv2.blur(block,(ws,ws)); sq=cv2.blur(block*block,(ws,ws))
lstd=np.sqrt(np.maximum(sq-blur*blur,0))
print("lstd pcts",{p:round(float(np.percentile(lstd,p)),1) for p in (10,30,50,70)})
print("int pcts",{p:round(float(np.percentile(block,p)),1) for p in (30,45,60,75)})
uni=((lstd<np.percentile(lstd,30))&(block>np.percentile(block,45))).astype(np.uint8)
kk=max(3,(ws//2)|1); k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(kk,kk))
uni2=cv2.morphologyEx(uni,cv2.MORPH_OPEN,k,1); uni2=cv2.morphologyEx(uni2,cv2.MORPH_CLOSE,k,2)
n,lab,stats,_=cv2.connectedComponentsWithStats(uni2,connectivity=8)
ba=block.size
print(f"components (area, areafrac, L,T,W,H, minwh):")
comps=sorted([(stats[i,cv2.CC_STAT_AREA],i) for i in range(1,n)],reverse=True)[:10]
for area,i in comps:
    L,T,W,H=stats[i,cv2.CC_STAT_LEFT],stats[i,cv2.CC_STAT_TOP],stats[i,cv2.CC_STAT_WIDTH],stats[i,cv2.CC_STAT_HEIGHT]
    print(f"  area={area} frac={area/ba:.3f} L={L} T={T} W={W} H={H} minwh={min(W,H)}")
ov=cv2.cvtColor(np.clip(block,0,255).astype(np.uint8),cv2.COLOR_GRAY2BGR)
red=ov.copy(); red[uni2>0]=(0,0,255)
cv2.imwrite(str(OUTDIR/"padmask_6B.png"),cv2.addWeighted(ov,0.55,red,0.45,0))
print("wrote padmask_6B.png")
