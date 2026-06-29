"""Sanity-check the isolation_clearance internals against the raw profile for the
AF200 6B pads, to confirm specular/clearance flags are real not artefacts."""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
import cv2, numpy as np
HERE = Path(__file__).resolve().parent; WA = HERE.parent; ROOT = WA.parent
sys.path.insert(0, str(ROOT / "tile-sharpness" / "src"))
from tile_sharpness.methods import pad_long_edge as ple
def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
RAW = Path("/home/alson/shared/files/pics/digikam/test-raw-data/2026-01-29")
jp = RAW/"Nikon AF Micro-Nikkor 200mm f_4D IF-ED"/"1_1"/"F8"/"00267|Nikon AF Micro-Nikkor 200mm f_4D IF-ED|1_1|200.0 mm|F8|alm-20260129-161423-267.jpg"
g=cv2.imread(str(jp),cv2.IMREAD_GRAYSCALE).astype(np.float32)
blk=(2095,4362,3363,5504)
pads=ple.find_bright_pad(g,blk)
for pi,pad in enumerate(pads[:2]):
    for side in ("top","bottom"):
        res=ple.refine_pad_hedge(g,pad,side=side)
        if res is None: print(f"pad{pi} {side} FAIL"); continue
        seg,off=res
        ds,prof=ple.perp_profile(g,seg,side,half=50)
        pc,oc,spec=ple.isolation_clearance(g,seg,pad,side)
        # print profile near edge
        s=" ".join(f"{int(d):+d}:{int(v)}" for d,v in zip(ds,prof) if -20<=d<=40 and abs(d)%2<0.5)
        print(f"\npad{pi} {side} off={off:.1f} -> pad_clear={pc:.0f} open_clear={oc:.0f} spec={spec}")
        print("  profile(+d=open,-d=pad):",s)
