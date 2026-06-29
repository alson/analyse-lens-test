"""For each registering 2:1 config, list ALL die TYPES (col%4,row%4) fully in FOV,
and specifically whether the 2B serpent type (2,1) is reachable. Also confirm the
FOV is fixed across the focus stack (these are focus stacks, not position sweeps)."""
from __future__ import annotations
import importlib.util, glob
from pathlib import Path
import numpy as np, cv2

WA = Path(__file__).resolve().parent
def _load(n):
    s = importlib.util.spec_from_file_location(n, WA / f"{n}.py"); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
ra = _load("reg_auto")
import sys; sys.path.insert(0, str(WA.parent.parent / "tile-sharpness" / "src"))
L = _load("lib_2b")
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
IMG_W, IMG_H = 8256, 5504
TYPE_NAME = {(0,0):"E-pads",(0,1):"B-3x3grid",(0,2):"C-pads",(0,3):"D-4Dbar",
             (1,0):"E",(1,1):"B-resistors",(1,2):"C-3band",(1,3):"D",
             (2,0):"E",(2,1):"2B-SERPENT",(2,2):"C",(2,3):"D",
             (3,0):"E",(3,1):"B",(3,2):"C",(3,3):"D"}

CFG = {
    "AF200+5T+6T": "Nikon AF Micro-Nikkor 200mm f_4D IF-ED + 5T + 6T/2_1/F11",
    "AF200+6T+5T": "Nikon AF Micro-Nikkor 200mm f_4D IF-ED + 6T + 5T/2_1/F11",
    "Sigma150+TC": "Sigma APO Macro 150mm F2.8 EX DG OS HSM + TC-2001/2_1/F11",
}


def dies_in_fov(aff, min_cov=0.85):
    out = []
    for col in range(11):
        for row in range(6):
            bx0,by0,bx1,by1 = L.block_bbox(col,row,aff)
            cx,cy = (bx0+bx1)/2,(by0+by1)/2
            if not (60<cx<IMG_W-60 and 60<cy<IMG_H-60): continue
            ix0,iy0,ix1,iy1 = max(0,bx0),max(0,by0),min(IMG_W,bx1),min(IMG_H,by1)
            cov = (ix1-ix0)*(iy1-iy0)/max(1,(bx1-bx0)*(by1-by0))
            if cov>=min_cov:
                out.append((col,row,(col%4,row%4),cov))
    return out


for name, sub in CFG.items():
    rmse, aff, jp, jpgs = L.register_best(RAW/sub)
    if aff is None:
        print(f"{name}: no reg"); continue
    M = aff["scale"]/ra.M_ANCHOR_SCALE
    dies = dies_in_fov(aff)
    types = sorted(set(d[2] for d in dies))
    print(f"\n{name}: M={M:.3f} rmse={rmse:.2f} col0={aff.get('reg_col_first')} row0={aff.get('reg_row_first')}")
    print(f"  dies fully in FOV: {[(f'{c}{chr(65+r)}',TYPE_NAME[t]) for c,r,t,_ in dies]}")
    print(f"  die TYPES in FOV: {[TYPE_NAME[t] for t in types]}")
    has2b = any(t==(2,1) for *_ ,t,_ in [(0,*d) for d in dies])
    print(f"  2B-SERPENT (2,1) fully framed: {(2,1) in types}")
    # also report partial 2B (centre in frame even if not 85% covered)
    part=[]
    for col in range(11):
        for row in range(6):
            if (col%4,row%4)!=(2,1): continue
            bx0,by0,bx1,by1=L.block_bbox(col,row,aff)
            cx,cy=(bx0+bx1)/2,(by0+by1)/2
            if 0<cx<IMG_W and 0<cy<IMG_H:
                ix0,iy0,ix1,iy1=max(0,bx0),max(0,by0),min(IMG_W,bx1),min(IMG_H,by1)
                cov=(ix1-ix0)*(iy1-iy0)/max(1,(bx1-bx0)*(by1-by0))
                part.append((f"{col}{chr(65+row)}",round(cov,2),int(cx),int(cy)))
    print(f"  2B dies w/ centre in frame (label,cov,cx,cy): {part}")
