"""Appearance-based two-pad die finder (independent of absolute die labelling).

The atlas (col%4,row%4)->type periodicity + reg_auto's absolute row label proved
unreliable for placing the 2B-type die (a whole-row offset shifts position by a
die pitch). Instead: enumerate EVERY in-FOV die cell from the registration grid,
crop each, and score it for the two-large-uniform-pads signature. Pick the best.

The signature: inside the die's central experimental block there are 1-2 LARGE,
LOW-LOCAL-VARIANCE (uniform metal) rectangles, much more uniform than the striped
serpent/comb surround and the speckly bond-pad borders. We score a cell by the
area of its largest low-local-std connected component (computed at a die-relative
scale so it works across magnifications)."""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
import cv2, numpy as np

HERE = Path(__file__).resolve().parent
WA = HERE.parent; ROOT = WA.parent
sys.path.insert(0, str(ROOT / "tile-sharpness" / "src"))
def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
reg_auto = _load("reg_auto")
ATLAS = json.load(open(WA / "atlas.json"))
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
IMAGE_W, IMAGE_H = 8256, 5504
M_ANCHOR_SCALE = 1.6549
EXP_BBOX_UV = (0.0, 0.266, 0.999, 0.881)
OUTDIR=HERE/"diag_2b_padedge_out"; OUTDIR.mkdir(exist_ok=True)

ap_dir = RAW / "Nikon AF Micro-Nikkor 200mm f_4D IF-ED" / "1_1" / "F8"
jpgs = sorted(ap_dir.glob("*.jpg"))
def central_lapvar(g):
    c = g[IMAGE_H//2-800:IMAGE_H//2+800, IMAGE_W//2-800:IMAGE_W//2+800]
    return cv2.Laplacian(c.astype(np.float32), cv2.CV_32F).var()
lv=[]
for jp in jpgs:
    g=cv2.imread(str(jp),cv2.IMREAD_GRAYSCALE); lv.append((central_lapvar(g) if g is not None else -1,jp))
lv.sort(reverse=True)
best=None
for jp in [j for _,j in lv[:6]]:
    p=reg_auto.register_and_refine("d",path=str(jp),anchors=None)
    if p and p.get("n_refine_intersections"):
        if best is None or p["reg_fit_rmse_px"]<best[0]: best=(p["reg_fit_rmse_px"],p,jp)
rmse,aff,jp=best
M=aff["scale"]/M_ANCHOR_SCALE
print(f"reg {jp.name} rmse={rmse:.2f} M={M:.3f}")
g=cv2.imread(str(jp),cv2.IMREAD_GRAYSCALE).astype(np.float32)

def block_bbox(col,row,aff):
    u0,v0,u1,v1=EXP_BBOX_UV
    cor=[reg_auto.grid_xy_distorted(col+u,row+v,aff) for u,v in [(u0,v0),(u0,v1),(u1,v0),(u1,v1)]]
    xs=[c[0] for c in cor]; ys=[c[1] for c in cor]
    return min(xs),min(ys),max(xs),max(ys)

def pad_score(block):
    h,w=block.shape
    if h<60 or w<60: return 0,None
    # local std over a die-relative window (~6% of block min-dim)
    ws=max(5,int(0.05*min(h,w)) | 1)
    blur=cv2.blur(block,(ws,ws)); sq=cv2.blur(block*block,(ws,ws))
    lstd=np.sqrt(np.maximum(sq-blur*blur,0))
    # uniform = lstd in lowest third AND not the very darkest (grooves are uniform-dark too,
    # but pads are mid/bright); require brightness above block median-ish
    uni=((lstd<np.percentile(lstd,30)) & (block>np.percentile(block,45))).astype(np.uint8)
    k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(max(3,ws//2)|1,max(3,ws//2)|1))
    uni=cv2.morphologyEx(uni,cv2.MORPH_OPEN,k,1)
    uni=cv2.morphologyEx(uni,cv2.MORPH_CLOSE,k,2)
    n,lab,stats,_=cv2.connectedComponentsWithStats(uni,connectivity=8)
    areas=sorted([(stats[i,cv2.CC_STAT_AREA],i) for i in range(1,n)],reverse=True)
    if not areas: return 0,None
    a0,i0=areas[0]
    s=stats[i0]
    return a0/(h*w), (int(s[cv2.CC_STAT_LEFT]),int(s[cv2.CC_STAT_TOP]),int(s[cv2.CC_STAT_WIDTH]),int(s[cv2.CC_STAT_HEIGHT]))

# enumerate ALL die cells in the grid (every col,row), score the experimental block
results=[]
for col in range(0,11):
    for row in range(0,6):
        bx0,by0,bx1,by1=block_bbox(col,row,aff)
        cx,cy=(bx0+bx1)/2,(by0+by1)/2
        if not (60<cx<IMAGE_W-60 and 60<cy<IMAGE_H-60): continue
        ix0,iy0=max(0,int(bx0)),max(0,int(by0)); ix1,iy1=min(IMAGE_W,int(bx1)),min(IMAGE_H,int(by1))
        if ix1-ix0<80 or iy1-iy0<80: continue
        frac=((ix1-ix0)*(iy1-iy0))/max(1,(bx1-bx0)*(by1-by0))
        if frac<0.85: continue
        block=g[iy0:iy1,ix0:ix1]
        sc,pb=pad_score(block)
        results.append((sc,col,row,(ix0,iy0,ix1,iy1),pb,col%4,row%4))
results.sort(reverse=True)
print("top-scoring die cells (score, col,row -> type col%4,row%4, padbbox):")
for sc,col,row,bb,pb,c4,r4 in results[:8]:
    lbl=f"{col}{'ABCDEF'[row]}"
    print(f"  {lbl} type=({c4},{r4}) score={sc:.3f} block={bb} padcomp={pb}")
    cb=g[bb[1]:bb[3],bb[0]:bb[2]]
    cv2.imwrite(str(OUTDIR/f"finddie_{lbl}_s{sc:.2f}.png"),np.clip(cb,0,255).astype(np.uint8))
