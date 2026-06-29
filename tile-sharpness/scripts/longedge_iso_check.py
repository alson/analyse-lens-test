"""Recentred-ESF MTF50 via BOTH erf and model-free ISO, L=80 & 120, left+right,
both bars, all configs. The erf over-reads on the lit (specular) wall; the ISO
crossing is the honest cross-check. Tests whether an ISO readout discriminates
while staying <= ceiling. JSONL out. Shard SHARD=i/n over configs."""
from __future__ import annotations
import importlib.util, sys, json, os, statistics
from pathlib import Path
import cv2, numpy as np
HERE=Path(__file__).resolve().parent; TS=HERE.parent; WA=TS.parent/"wafer-atlas"
sys.path.insert(0,str(TS/"src"))
from tile_sharpness.methods import slanted_edge as SE
from tile_sharpness.methods.long_edge import refine_bar_edge, subsegment
from tile_sharpness import optics
_s=importlib.util.spec_from_file_location("reg_auto",WA/"scripts"/"reg_auto.py"); reg_auto=importlib.util.module_from_spec(_s); _s.loader.exec_module(reg_auto)
_a=importlib.util.spec_from_file_location("acm",HERE/"atlas_corner_mtf.py"); acm=importlib.util.module_from_spec(_a); _a.loader.exec_module(acm)
ATLAS=json.load(open(WA/"atlas.json")); RAW=Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
BB=ATLAS["die_types"]["(0, 3)"]["feature_inventory"]["slanted_edge"][0]["bbox_uv"]
IW,IH=8256,5504; LPMM=229.9
OUT=Path(os.environ.get("OUT",TS/"out_longedge_iso")); OUT.mkdir(parents=True,exist_ok=True)
from longedge_experiment import CONFIGS

def bars(p):
    u0,v0,u1,v1=BB;o=[]
    for col in range(11):
        for row in range(6):
            if (col%4,row%4)!=(0,3):continue
            proj=(lambda u,v: reg_auto.grid_xy_distorted(col+u,row+v,p)) if "k1" in p else (lambda u,v: reg_auto.af.grid_xy(col+u,row+v,p,ATLAS))
            cs=[proj(u,v) for u,v in[(u0,v0),(u0,v1),(u1,v0),(u1,v1)]]
            xs=[c[0]for c in cs];ys=[c[1]for c in cs];m=90
            if m<min(xs)and max(xs)<IW-m and m<min(ys)and max(ys)<IH-m:o.append((col,row,(min(xs),min(ys),max(xs),max(ys))))
    return o

def measure(label,rel,N,tier,rows):
    d=RAW/rel; jp=sorted(d.glob("*.jpg"))
    if not jp: rows.append(dict(config=label,status="no_jpgs"));return
    aff=acm.register(jp)
    if aff is None: rows.append(dict(config=label,status="reg_failed"));return
    M=aff["scale"]/acm.M_ANCHOR_SCALE; ceil=optics.diffraction_mtf50_sensor_lpmm(N*(1+M))/LPMM
    for col,row,bb in bars(aff):
        cx,cy=(bb[0]+bb[2])/2,(bb[1]+bb[3])/2
        best=(-1,None)
        for j in jp:
            g=cv2.imread(str(j),0)
            if g is None:continue
            lv=acm.roi_lapvar(g,int(cx),int(cy),half=90)
            if lv>best[0]:best=(lv,g)
        g=best[1].astype(np.float32)
        for side in("left","right"):
            r=refine_bar_edge(g,bb,side=side)
            if r is None:continue
            seg,off=r
            for L in (80,120):
                sub=subsegment(seg,L); out=SE.superres_esf_recentred(g,sub,half_window_px=16)
                if out is None:continue
                c,e=out; m_erf=SE._fit_wall(c,e); m_iso=SE._iso_wall(e,4.0)
                rows.append(dict(config=label,tier=tier,M=round(M,4),ceil=round(ceil,4),
                    die=f"c{col}r{row}",side=side,L=L,
                    erf=(round(m_erf,4) if m_erf else None),iso=(round(m_iso,4) if m_iso else None),
                    erf_x=(round(m_erf/ceil,2) if m_erf else None),iso_x=(round(m_iso/ceil,2) if m_iso else None),
                    status="ok"))

def main():
    i,n=(int(x) for x in os.environ.get("SHARD","0/1").split("/"))
    rows=[]
    for idx,cfg in enumerate(CONFIGS):
        if idx%n!=i:continue
        try: measure(*cfg,rows)
        except Exception as ex: rows.append(dict(config=cfg[0],status=f"err:{ex}"))
        print(f"[{i}/{n}] {cfg[0]} done",flush=True)
    with open(OUT/f"shard_{i}of{n}.jsonl","w") as f:
        for r in rows: f.write(json.dumps(r)+"\n")
if __name__=="__main__": main()
