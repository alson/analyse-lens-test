"""Check registration stability: for several candidate frames of AF200 1:1 F8,
register and dump the (2,1)-type die block bbox + a crop, to see if the pad-block
mapping is stable or row-label-ambiguous."""
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
cands=[j for _,j in lv[:6]]
def block_bbox(col,row,aff):
    u0,v0,u1,v1=EXP_BBOX_UV
    corners=[reg_auto.grid_xy_distorted(col+u,row+v,aff) for u,v in [(u0,v0),(u0,v1),(u1,v0),(u1,v1)]]
    xs=[c[0] for c in corners]; ys=[c[1] for c in corners]
    return min(xs),min(ys),max(xs),max(ys)
for jp in cands:
    p=reg_auto.register_and_refine("d",path=str(jp),anchors=None)
    if p is None or not p.get("n_refine_intersections"):
        print(jp.name,"reg fail"); continue
    M=p["scale"]/M_ANCHOR_SCALE
    print(f"\n{jp.name}: rmse={p['reg_fit_rmse_px']:.2f} M={M:.3f} col_first={p.get('reg_col_first')} row_first={p.get('reg_row_first')}")
    g=cv2.imread(str(jp),cv2.IMREAD_GRAYSCALE).astype(np.float32)
    for col in (2,6,10):
        for row in (1,5):
            bx0,by0,bx1,by1=block_bbox(col,row,p)
            cx,cy=(bx0+bx1)/2,(by0+by1)/2
            if 80<cx<IMAGE_W-80 and 80<cy<IMAGE_H-80:
                lbl=f"{col}{'ABCDEF'[row]}"
                print(f"   die {lbl}: block ({bx0:.0f},{by0:.0f},{bx1:.0f},{by1:.0f})")
                cb=g[max(0,int(by0)):min(IMAGE_H,int(by1)),max(0,int(bx0)):min(IMAGE_W,int(bx1))]
                if cb.size:
                    cv2.imwrite(str(OUTDIR/f"regcheck_{jp.name.split('|')[0]}_{lbl}.png"),np.clip(cb,0,255).astype(np.uint8))
