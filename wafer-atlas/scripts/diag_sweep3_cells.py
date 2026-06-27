"""Does sweep3's FOV actually contain a cell where the fragment map differs
between col_first=1 and col_first=5? If yes, the 'no nick visible' argument can
resolve it; if both are all-whole in view, it's genuinely ambiguous at this M.
Dump per-cell observed coverage vs map(col1) vs map(col5)."""
import importlib.util, json
from pathlib import Path
import numpy as np

HERE = Path(__file__).parent; A = HERE.parent
def _load(m,f):
    s=importlib.util.spec_from_file_location(m,HERE/f); x=importlib.util.module_from_spec(s); s.loader.exec_module(x); return x
af=_load("af","anchor_fit_sweep.py"); ra=_load("ra","reg_auto.py"); fm=_load("fm","diag_fragment_match.py")
ATLAS=json.load(open(A/"atlas.json")); FMAP=json.load(open(A/"out"/"fragment_map.json"))["coverage"]

name="sweep3_M2.0"; path,anchors=ra.SWEEPS[name]
det=ra.detect(path); wafer,_=fm.sweep_wafer_fullres(path)
col_x,row_y=det["col_x"],det["row_y"]; H,W=wafer.shape

for cf in (1,5):
    cl=[cf+i for i in range(len(col_x))]; rl_top=2+(len(row_y)-1)
    pairs=[(cl[ci],rl_top-ri,*ra.derot_to_orig(float(xd),float(yd),det)) for ci,xd in enumerate(col_x) for ri,yd in enumerate(row_y)]
    p=af.fit_sweep_affine(pairs,ATLAS,theta_init_deg=det["tilt"],scale_init=0.5)
    print(f"\n=== col_first={cf} ===  (visible cells: observed | map)")
    # include cells whose center OR a u/v-edge sample is in frame, to catch partial boundary cells
    for row in range(6):
        line=[]
        for col in range(11):
            x,y=af.grid_xy(col+0.5,row+0.5,p,ATLAS)
            if not (0<x<W and 0<y<H):
                # check if any corner in-frame (partial/boundary cell)
                corners=[af.grid_xy(col+u,row+v,p,ATLAS) for u in(0.1,0.9) for v in(0.1,0.9)]
                if not any(0<cx<W and 0<cy<H for cx,cy in corners):
                    continue
            o=fm._observed_cov(wafer,p,col,row) if hasattr(fm,"_observed_cov") else ra._observed_cov(wafer,p,col,row)
            m=FMAP.get(f"{col},{row}")
            tag="*" if (m is not None and m<0.9) else " "
            line.append(f"{col}{'ABCDEF'[row]}{tag}o{o:.2f}/m{m if m is None else round(m,2)}")
        if line: print("  "+"  ".join(line))
print("\n(* = map says this cell is nicked/partial; if visible & observed whole, rules that offset out)")
